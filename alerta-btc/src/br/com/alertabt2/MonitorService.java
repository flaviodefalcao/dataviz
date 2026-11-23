package br.com.alertabt2;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.media.AudioAttributes;
import android.media.MediaPlayer;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.os.VibrationEffect;
import android.os.Vibrator;

import java.text.SimpleDateFormat;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public final class MonitorService extends Service {
    static final String ACTION_REFRESH = "br.com.alertabt2.REFRESH";
    static final String ACTION_SILENCE = "br.com.alertabt2.SILENCE";
    static final String ACTION_STOP = "br.com.alertabt2.STOP";

    static final int MONITOR_ID = 41;
    static final int ALERT_ID = 42;
    private static final String CHANNEL_MONITOR = "btc_monitor_silent_v2";
    private static final String CHANNEL_ALERT = "btc_alert";

    /** Intervalo de checagem dentro do horário de alarme e fora dele. */
    private static final long INTERVAL_ACTIVE_S = 60;
    private static final long INTERVAL_IDLE_S = 5 * 60;
    private static final long AUTO_SILENCE_MS = 30_000;
    private static final long[] VIBRATION = {0, 400, 300, 400, 600};

    /** Indica à tela se o serviço está vivo (para reiniciar depois de o sistema matar o app). */
    static volatile boolean running;

    private final Handler main = new Handler(Looper.getMainLooper());
    private ScheduledExecutorService executor;
    private ScheduledFuture<?> nextCheck;
    private PowerManager.WakeLock wakeLock;
    private MediaPlayer player;
    private Vibrator vibrator;
    private boolean started;

    private final Runnable checkTask = new Runnable() {
        @Override public void run() { checkPrice(); }
    };
    private final Runnable silenceTask = new Runnable() {
        @Override public void run() { silence(); }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        NotificationManager nm = getSystemService(NotificationManager.class);
        NotificationChannel monitor = new NotificationChannel(CHANNEL_MONITOR, "Monitoramento BTC",
                NotificationManager.IMPORTANCE_LOW);
        monitor.setDescription("Estado do monitoramento de preço");
        monitor.setSound(null, null);
        monitor.enableVibration(false);
        monitor.setShowBadge(false);
        nm.createNotificationChannel(monitor);
        NotificationChannel alert = new NotificationChannel(CHANNEL_ALERT, "Alarmes BTC",
                NotificationManager.IMPORTANCE_HIGH);
        alert.setDescription("Avisos de preço atingido");
        alert.setSound(null, null); // o som é tocado pelo próprio app, conforme configuração
        alert.enableVibration(false);
        nm.createNotificationChannel(alert);
        executor = Executors.newSingleThreadScheduledExecutor();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent != null && intent.getAction() != null ? intent.getAction() : "";
        SharedPreferences prefs = AlertStore.prefs(this);

        if (ACTION_SILENCE.equals(action)) {
            silence();
            getSystemService(NotificationManager.class).cancel(ALERT_ID);
            if (!started) stopSelf(startId);
            return started ? START_STICKY : START_NOT_STICKY;
        }
        if (ACTION_STOP.equals(action)) {
            prefs.edit().putBoolean(AlertStore.KEY_MONITORING, false)
                    .putString(AlertStore.KEY_STATUS, "Monitoramento desligado").apply();
            shutdown();
            return START_NOT_STICKY;
        }

        // Se foi iniciado com startForegroundService(), é obrigatório chamar startForeground()
        // antes de parar; caso contrário o Android encerra o app com erro.
        if (!started && !goForeground()) {
            prefs.edit().putBoolean(AlertStore.KEY_MONITORING, false)
                    .putString(AlertStore.KEY_STATUS, "O Android bloqueou o monitoramento. Abra o app e ligue de novo.")
                    .apply();
            stopSelf();
            return START_NOT_STICKY;
        }
        if (!prefs.getBoolean(AlertStore.KEY_MONITORING, false)) {
            shutdown();
            return START_NOT_STICKY;
        }
        if (!started) {
            started = true;
            running = true;
            PowerManager pm = getSystemService(PowerManager.class);
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "AlertaBTC:Monitoramento");
            wakeLock.setReferenceCounted(false);
            wakeLock.acquire();
            scheduleCheck(0);
        } else if (ACTION_REFRESH.equals(action)) {
            scheduleCheck(0);
        }
        return START_STICKY;
    }

    private boolean goForeground() {
        try {
            Notification n = monitorNotification(AlertStore.prefs(this));
            if (Build.VERSION.SDK_INT >= 29) {
                startForeground(MONITOR_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
            } else {
                startForeground(MONITOR_ID, n);
            }
            return true;
        } catch (RuntimeException e) { // ForegroundServiceStartNotAllowedException (Android 12+)
            return false;
        }
    }

    private synchronized void scheduleCheck(long delaySeconds) {
        if (executor == null || executor.isShutdown()) return;
        if (nextCheck != null) nextCheck.cancel(false);
        nextCheck = executor.schedule(checkTask, delaySeconds, TimeUnit.SECONDS);
    }

    private void checkPrice() {
        SharedPreferences prefs = AlertStore.prefs(this);
        if (!prefs.getBoolean(AlertStore.KEY_MONITORING, false)) return;
        boolean inHours = isInHours(prefs);
        try {
            long now = System.currentTimeMillis();
            PriceClient.Quote q;
            try {
                q = PriceClient.fetchWithRetry();
            } catch (Exception e) {
                updateStatus("Falha ao buscar cotação: " + e.getClass().getSimpleName(), now);
                return;
            }
            if (!ThresholdEvaluator.isFresh(q.timeMs, now)) {
                updateStatus("Cotação com mais de 10 min ou horário inválido", now);
                return;
            }
            AlertStore.saveQuote(this, q);
            BtcWidgetProvider.updateAll(this);

            List<AlertStore.Alert> alerts = AlertStore.load(this);
            List<AlertStore.Alert> fired = new ArrayList<>();
            boolean changed = false;
            for (AlertStore.Alert a : alerts) {
                boolean hit = ThresholdEvaluator.condition(q.price, a.target, a.above);
                if (!hit && !a.armed) {          // preço voltou ao outro lado: rearma
                    a.armed = true;
                    changed = true;
                } else if (hit && a.armed && inHours) {
                    a.armed = false;
                    fired.add(a);
                    changed = true;
                }
            }
            if (changed) AlertStore.save(this, alerts);
            updateStatus(inHours ? "Cotação atualizada" : "Fora do horário dos alarmes", now);
            refreshMonitorNotification(prefs);

            if (!fired.isEmpty() && prefs.getBoolean(AlertStore.KEY_MONITORING, false)) {
                final List<AlertStore.Alert> hits = fired;
                final double price = q.price;
                main.post(new Runnable() {
                    @Override public void run() { ring(hits, price); }
                });
            }
        } finally {
            // Fora do horário de alarme não há o que tocar: consulta com menos frequência.
            scheduleCheck(inHours ? INTERVAL_ACTIVE_S : INTERVAL_IDLE_S);
        }
    }

    private static boolean isInHours(SharedPreferences p) {
        if (!p.getBoolean(AlertStore.KEY_WINDOW, false)) return true;
        try {
            return ThresholdEvaluator.inWindow(LocalTime.now(),
                    LocalTime.parse(p.getString(AlertStore.KEY_START, "00:00")),
                    LocalTime.parse(p.getString(AlertStore.KEY_END, "00:00")));
        } catch (Exception e) {
            return true;
        }
    }

    private void updateStatus(String status, long time) {
        AlertStore.prefs(this).edit().putString(AlertStore.KEY_STATUS, status)
                .putLong(AlertStore.KEY_CHECK_TIME, time).apply();
    }

    private Notification monitorNotification(SharedPreferences prefs) {
        PendingIntent open = PendingIntent.getActivity(this, 1,
                new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        PendingIntent stop = PendingIntent.getService(this, 2,
                new Intent(this, MonitorService.class).setAction(ACTION_STOP),
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        double price = AlertStore.lastPrice(prefs);
        long t = prefs.getLong(AlertStore.KEY_TRADE_TIME, 0);
        String text = price > 0 && t > 0
                ? String.format(Locale.US, "US$ %,.2f", price) + " · "
                  + new SimpleDateFormat("HH:mm", Locale.getDefault()).format(new Date(t))
                : "Monitorando os preços cadastrados";
        Notification.Builder b = new Notification.Builder(this, CHANNEL_MONITOR)
                .setSmallIcon(android.R.drawable.stat_notify_sync_noanim)
                .setContentTitle("Alerta BTC ligado")
                .setContentText(text)
                .setContentIntent(open)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setShowWhen(false)
                .setCategory(Notification.CATEGORY_SERVICE)
                .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Desligar", stop);
        if (Build.VERSION.SDK_INT >= 31) {
            b.setForegroundServiceBehavior(Notification.FOREGROUND_SERVICE_IMMEDIATE);
        }
        return b.build();
    }

    private void refreshMonitorNotification(SharedPreferences prefs) {
        if (!started) return;
        try {
            getSystemService(NotificationManager.class).notify(MONITOR_ID, monitorNotification(prefs));
        } catch (RuntimeException ignored) {
        }
    }

    private void ring(List<AlertStore.Alert> hits, double price) {
        SharedPreferences prefs = AlertStore.prefs(this);
        if (!prefs.getBoolean(AlertStore.KEY_MONITORING, false)) return;
        silence();

        String title = hits.size() == 1
                ? "BTC atingiu " + String.format(Locale.US, "US$ %,.2f", hits.get(0).target)
                : "BTC atingiu " + hits.size() + " alertas";
        String body = String.format(Locale.US, "Cotação atual: US$ %,.2f", price);

        if (prefs.getBoolean(AlertStore.KEY_ALERT_NOTIFICATION, true)) {
            PendingIntent open = PendingIntent.getActivity(this, 3,
                    new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            PendingIntent mute = PendingIntent.getService(this, 4,
                    new Intent(this, MonitorService.class).setAction(ACTION_SILENCE),
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            try {
                getSystemService(NotificationManager.class).notify(ALERT_ID,
                        new Notification.Builder(this, CHANNEL_ALERT)
                                .setSmallIcon(android.R.drawable.stat_sys_warning)
                                .setContentTitle(title)
                                .setContentText(body)
                                .setContentIntent(open)
                                .setDeleteIntent(mute)
                                .setAutoCancel(true)
                                .setCategory(Notification.CATEGORY_ALARM)
                                .addAction(android.R.drawable.ic_lock_silent_mode, "Silenciar", mute)
                                .build());
            } catch (RuntimeException ignored) {
            }
        }

        if (prefs.getBoolean(AlertStore.KEY_SOUND_ENABLED, true)) {
            String custom = prefs.getString(AlertStore.KEY_SOUND, "");
            Uri first = custom.isEmpty()
                    ? RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM) : Uri.parse(custom);
            playSound(first, true);
        }

        if (prefs.getBoolean(AlertStore.KEY_VIBRATE, true)) {
            vibrator = getSystemService(Vibrator.class);
            if (vibrator != null && vibrator.hasVibrator()) {
                vibrator.vibrate(VibrationEffect.createWaveform(VIBRATION, 0));
            }
        }
        main.removeCallbacks(silenceTask);
        main.postDelayed(silenceTask, AUTO_SILENCE_MS);
    }

    /** Toca em loop sem travar a thread principal; se o som falhar, cai no toque de notificação. */
    private void playSound(Uri uri, final boolean allowFallback) {
        releasePlayer();
        if (uri == null) {
            if (allowFallback) playSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION), false);
            return;
        }
        final MediaPlayer mp = new MediaPlayer();
        player = mp;
        try {
            mp.setAudioAttributes(new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build());
            mp.setDataSource(this, uri);
            mp.setLooping(true);
            mp.setOnPreparedListener(new MediaPlayer.OnPreparedListener() {
                @Override public void onPrepared(MediaPlayer p) {
                    if (player == p) p.start();
                }
            });
            mp.setOnErrorListener(new MediaPlayer.OnErrorListener() {
                @Override public boolean onError(MediaPlayer p, int what, int extra) {
                    if (player == p && allowFallback) {
                        playSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION), false);
                    } else if (player == p) {
                        releasePlayer();
                    }
                    return true;
                }
            });
            mp.prepareAsync();
        } catch (Exception e) {
            releasePlayer();
            if (allowFallback) playSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION), false);
        }
    }

    private void releasePlayer() {
        MediaPlayer mp = player;
        player = null;
        if (mp != null) {
            try {
                mp.stop();
            } catch (Exception ignored) {
            }
            mp.release();
        }
    }

    private void silence() {
        main.removeCallbacks(silenceTask);
        releasePlayer();
        if (vibrator != null) {
            vibrator.cancel();
            vibrator = null;
        }
    }

    private void shutdown() {
        silence();
        if (Build.VERSION.SDK_INT >= 24) stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    @Override
    public void onDestroy() {
        running = false;
        started = false;
        silence();
        if (executor != null) executor.shutdownNow();
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
