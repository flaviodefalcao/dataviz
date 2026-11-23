package br.com.alertabt2;

import android.Manifest;
import android.app.Activity;
import android.app.NotificationManager;
import android.app.TimePickerDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.Ringtone;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CompoundButton;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.TimePicker;
import android.widget.Toast;

import java.text.NumberFormat;
import java.time.Instant;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int INK = Color.rgb(25, 35, 50);
    private static final int MUTED = Color.rgb(105, 116, 130);
    private static final int BLUE = Color.rgb(35, 94, 214);
    private static final int BG = Color.rgb(245, 247, 251);
    private static final int SOFT_BLUE = Color.rgb(235, 241, 253);
    private static final DateTimeFormatter CLOCK = DateTimeFormatter.ofPattern("HH:mm");
    private static final DateTimeFormatter STAMP = DateTimeFormatter
            .ofPattern("dd/MM HH:mm:ss", new Locale("pt", "BR")).withZone(ZoneId.systemDefault());
    private static final long STALE_MS = 10 * 60_000L;
    private static final int PICK_SOUND = 7;
    private static final int REQUEST_NOTIFICATIONS = 8;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private SharedPreferences prefs;
    private boolean refreshing;

    private LinearLayout alertsContainer;
    private Spinner directionSpinner;
    private EditText targetInput;
    private TextView priceText, quoteTimeText, statusText, soundText;
    private Button startButton, startTimeButton, endTimeButton;
    private Switch notificationSwitch;

    /** Atualiza a tela só quando algo muda nas preferências (em vez de varrer a cada 2 s). */
    private final SharedPreferences.OnSharedPreferenceChangeListener prefListener =
            new SharedPreferences.OnSharedPreferenceChangeListener() {
                @Override public void onSharedPreferenceChanged(SharedPreferences p, String key) {
                    if (AlertStore.KEY_ALERTS.equals(key)) renderAlerts();
                    else updateLiveFields();
                }
            };
    /** Reavalia "cotação antiga / sem verificação" de vez em quando, mesmo sem mudanças. */
    private final Runnable staleTicker = new Runnable() {
        @Override public void run() {
            updateLiveFields();
            handler.postDelayed(this, 30_000);
        }
    };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = AlertStore.prefs(this);
        getWindow().setStatusBarColor(BG);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
        buildUi();
        renderAlerts();
        updateLiveFields();
        refreshPrice();
    }

    @Override
    protected void onResume() {
        super.onResume();
        prefs.registerOnSharedPreferenceChangeListener(prefListener);
        handler.post(staleTicker);
        // O sistema pode ter matado o serviço (economia de bateria, reinício do celular).
        if (prefs.getBoolean(AlertStore.KEY_MONITORING, false) && !MonitorService.running) {
            startMonitor(MonitorService.ACTION_REFRESH);
        }
        renderAlerts();
    }

    @Override
    protected void onPause() {
        prefs.unregisterOnSharedPreferenceChangeListener(prefListener);
        handler.removeCallbacks(staleTicker);
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        io.shutdownNow();
        super.onDestroy();
    }

    // ---------------------------------------------------------------- UI

    private void buildUi() {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BG);
        LinearLayout root = vertical();
        root.setPadding(dp(20), dp(24), dp(20), dp(32));
        scroll.addView(root);
        setContentView(scroll);

        root.addView(text("Alerta BTC", 30, INK, true));
        root.addView(text("Avise-me quando o BTC chegar ao meu preço", 14, MUTED, false));
        gap(root, 18);

        LinearLayout priceCard = card(root);
        priceCard.addView(text("BTC / USD  ·  Coinbase", 13, MUTED, true));
        gap(priceCard, 8);
        priceText = text("US$ —", 34, INK, true);
        priceCard.addView(priceText);
        quoteTimeText = text("Buscando cotação…", 13, MUTED, false);
        priceCard.addView(quoteTimeText);
        gap(priceCard, 10);
        statusText = text("", 13, BLUE, false);
        priceCard.addView(statusText);
        gap(priceCard, 10);
        LinearLayout row = horizontal();
        Button refresh = button("Atualizar agora", false);
        Button desk = button("Trade Desk ↗", false);
        row.addView(refresh, new LinearLayout.LayoutParams(0, dp(48), 1f));
        gapHorizontal(row, 8);
        row.addView(desk, new LinearLayout.LayoutParams(0, dp(48), 1f));
        priceCard.addView(row);
        refresh.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { refreshPrice(); }
        });
        desk.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                startActivity(new Intent(MainActivity.this, TradeDeskActivity.class));
            }
        });

        section(root, "Meus alertas");
        LinearLayout alertsCard = card(root);
        alertsContainer = vertical();
        alertsCard.addView(alertsContainer);
        targetInput = new EditText(this);
        targetInput.setSingleLine(true);
        targetInput.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        targetInput.setHint("Preço em USD, sem separador de milhar");
        targetInput.setTextSize(17);
        alertsCard.addView(targetInput, new LinearLayout.LayoutParams(-1, dp(52)));
        directionSpinner = new Spinner(this);
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item,
                new String[]{"Subiu até ou passou de", "Caiu até ou abaixo de"});
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        directionSpinner.setAdapter(adapter);
        alertsCard.addView(directionSpinner);
        gap(alertsCard, 8);
        Button add = button("Adicionar alerta", true);
        alertsCard.addView(add);
        add.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { addAlert(); }
        });
        gap(alertsCard, 8);
        alertsCard.addView(text("Cada alerta toca uma vez e rearma quando o preço volta ao outro lado do limite.", 12, MUTED, false));

        section(root, "Quando tocar");
        LinearLayout whenCard = card(root);
        final Switch windowSwitch = toggle(whenCard, "Usar horário diário", AlertStore.KEY_WINDOW, false);
        LinearLayout times = horizontal();
        startTimeButton = button("Início  " + prefs.getString(AlertStore.KEY_START, "00:00"), false);
        endTimeButton = button("Fim  " + prefs.getString(AlertStore.KEY_END, "00:00"), false);
        times.addView(startTimeButton, new LinearLayout.LayoutParams(0, dp(48), 1f));
        gapHorizontal(times, 8);
        times.addView(endTimeButton, new LinearLayout.LayoutParams(0, dp(48), 1f));
        whenCard.addView(times);
        startTimeButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { pickTime(AlertStore.KEY_START, startTimeButton, "Início  "); }
        });
        endTimeButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { pickTime(AlertStore.KEY_END, endTimeButton, "Fim  "); }
        });
        windowSwitch.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
            @Override public void onCheckedChanged(CompoundButton b, boolean on) {
                prefs.edit().putBoolean(AlertStore.KEY_WINDOW, on).apply();
                nudgeMonitor();
            }
        });
        gap(whenCard, 7);
        whenCard.addView(text("Horários iguais deixam o dia inteiro ativo. O intervalo pode atravessar a meia-noite. Fora do horário o app consulta a cada 5 min para poupar bateria.", 12, MUTED, false));

        section(root, "Avisos de preço");
        LinearLayout notifyCard = card(root);
        notificationSwitch = toggle(notifyCard, "Mostrar aviso ao atingir o preço", AlertStore.KEY_ALERT_NOTIFICATION, true);
        notificationSwitch.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
            @Override public void onCheckedChanged(CompoundButton b, boolean on) {
                prefs.edit().putBoolean(AlertStore.KEY_ALERT_NOTIFICATION, on).apply();
                if (on) requestNotificationsIfNeeded();
                else getSystemService(NotificationManager.class).cancel(MonitorService.ALERT_ID);
            }
        });
        bindToggle(toggle(notifyCard, "Tocar alarme ao atingir o preço", AlertStore.KEY_SOUND_ENABLED, true), AlertStore.KEY_SOUND_ENABLED);
        soundText = text(prefs.getString(AlertStore.KEY_SOUND_NAME, "Alarme padrão do celular"), 15, INK, false);
        notifyCard.addView(soundText);
        Button pick = button("Escolher som", false);
        notifyCard.addView(pick);
        pick.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { pickSound(); }
        });
        bindToggle(toggle(notifyCard, "Vibrar também", AlertStore.KEY_VIBRATE, true), AlertStore.KEY_VIBRATE);
        gap(notifyCard, 7);
        notifyCard.addView(text("Atualizações de preço são silenciosas. O alarme toca apenas ao atingir um preço cadastrado, conforme suas configurações.", 12, MUTED, false));

        gap(root, 24);
        startButton = button("Ligar monitoramento", true);
        root.addView(startButton, new LinearLayout.LayoutParams(-1, dp(56)));
        startButton.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { toggleMonitoring(); }
        });
        gap(root, 10);
        TextView foot = text("Consulta a cada 1 minuto enquanto ligado. O Android mostra uma notificação contínua. Deixe a internet ativa.", 12, MUTED, false);
        foot.setGravity(Gravity.CENTER);
        root.addView(foot);
    }

    private Switch toggle(LinearLayout parent, String label, String key, boolean def) {
        Switch s = new Switch(this);
        s.setText(label);
        s.setTextColor(INK);
        s.setTextSize(15);
        s.setMinHeight(dp(48));
        s.setChecked(prefs.getBoolean(key, def));
        parent.addView(s);
        return s;
    }

    private void bindToggle(Switch s, final String key) {
        s.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
            @Override public void onCheckedChanged(CompoundButton b, boolean on) {
                prefs.edit().putBoolean(key, on).apply();
            }
        });
    }

    private void renderAlerts() {
        if (alertsContainer == null) return;
        alertsContainer.removeAllViews();
        List<AlertStore.Alert> alerts = AlertStore.load(this);
        if (alerts.isEmpty()) {
            alertsContainer.addView(text("Nenhum preço cadastrado ainda.", 14, MUTED, false));
            gap(alertsContainer, 12);
            return;
        }
        for (final AlertStore.Alert a : alerts) {
            LinearLayout line = horizontal();
            line.setGravity(Gravity.CENTER_VERTICAL);
            LinearLayout labels = vertical();
            labels.addView(text((a.above ? "↑ " : "↓ ") + money(a.target), 17, INK, true));
            labels.addView(text(a.armed ? "Armado" : "Disparado · rearma ao voltar", 12, a.armed ? MUTED : BLUE, false));
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, -2, 1f);
            lp.topMargin = dp(6);
            lp.bottomMargin = dp(6);
            line.addView(labels, lp);
            Button del = button("Excluir", false);
            line.addView(del);
            del.setOnClickListener(new View.OnClickListener() {
                @Override public void onClick(View v) { removeAlert(a.id); }
            });
            alertsContainer.addView(line);
        }
        gap(alertsContainer, 8);
    }

    private void updateLiveFields() {
        if (priceText == null) return;
        double price = AlertStore.lastPrice(prefs);
        priceText.setText(price > 0 ? money(price) : "US$ —");
        long trade = prefs.getLong(AlertStore.KEY_TRADE_TIME, 0);
        if (trade > 0) {
            boolean fresh = ThresholdEvaluator.isFresh(trade, System.currentTimeMillis());
            quoteTimeText.setText((fresh ? "Último negócio: " : "Cotação antiga: ")
                    + STAMP.format(Instant.ofEpochMilli(trade)));
        } else {
            quoteTimeText.setText("Nenhuma cotação recebida");
        }
        boolean monitoring = prefs.getBoolean(AlertStore.KEY_MONITORING, false);
        boolean stuck = monitoring && System.currentTimeMillis()
                - prefs.getLong(AlertStore.KEY_CHECK_TIME, 0) > STALE_MS;
        String status = prefs.getString(AlertStore.KEY_STATUS, "Aguardando cotação");
        statusText.setText(stuck ? "Sem verificação há mais de 10 min. Toque para reiniciar." : status);
        startButton.setText(stuck ? "Reiniciar monitoramento"
                : monitoring ? "Desligar monitoramento" : "Ligar monitoramento");
        startButton.setBackground(shape(monitoring ? INK : BLUE, 12));
    }

    // ---------------------------------------------------------------- ações

    private void addAlert() {
        double target;
        try {
            target = Double.parseDouble(targetInput.getText().toString().trim().replace(',', '.'));
        } catch (NumberFormatException e) {
            targetInput.setError("Digite um preço válido");
            return;
        }
        if (!(target > 0) || target > 10_000_000 || Double.isInfinite(target)) {
            targetInput.setError("Digite um valor entre 0 e 10 milhões");
            return;
        }
        boolean above = directionSpinner.getSelectedItemPosition() == 0;
        // Não arma um alerta que já estaria disparado na hora de criar
        double now = AlertStore.lastPrice(prefs);
        boolean armed = !(now > 0 && ThresholdEvaluator.condition(now, target, above)
                && ThresholdEvaluator.isFresh(prefs.getLong(AlertStore.KEY_TRADE_TIME, 0), System.currentTimeMillis()));
        List<AlertStore.Alert> alerts = AlertStore.load(this);
        alerts.add(new AlertStore.Alert(System.currentTimeMillis(), target, above, armed));
        AlertStore.save(this, alerts);
        targetInput.setText("");
        renderAlerts();
        if (!armed) {
            Toast.makeText(this, "O preço já está desse lado: o alerta arma quando voltar.", Toast.LENGTH_LONG).show();
        }
    }

    private void removeAlert(long id) {
        List<AlertStore.Alert> alerts = AlertStore.load(this);
        for (Iterator<AlertStore.Alert> it = alerts.iterator(); it.hasNext(); ) {
            if (it.next().id == id) it.remove();
        }
        AlertStore.save(this, alerts);
        renderAlerts();
    }

    private void refreshPrice() {
        if (prefs.getBoolean(AlertStore.KEY_MONITORING, false) && MonitorService.running) {
            startService(new Intent(this, MonitorService.class).setAction(MonitorService.ACTION_REFRESH));
            return;
        }
        if (refreshing) return;
        refreshing = true;
        statusText.setText("Buscando cotação…");
        io.execute(new Runnable() {
            @Override public void run() {
                String status;
                try {
                    PriceClient.Quote q = PriceClient.fetchWithRetry();
                    if (ThresholdEvaluator.isFresh(q.timeMs, System.currentTimeMillis())) {
                        AlertStore.saveQuote(MainActivity.this, q);
                        BtcWidgetProvider.updateAll(MainActivity.this);
                        status = "Cotação atualizada";
                    } else {
                        status = "Cotação com mais de 10 min ou horário inválido";
                    }
                } catch (Exception e) {
                    status = "Falha ao buscar cotação: " + e.getClass().getSimpleName();
                }
                prefs.edit().putString(AlertStore.KEY_STATUS, status)
                        .putLong(AlertStore.KEY_CHECK_TIME, System.currentTimeMillis()).apply();
                runOnUiThread(new Runnable() {
                    @Override public void run() {
                        refreshing = false;
                        updateLiveFields();
                    }
                });
            }
        });
    }

    private void toggleMonitoring() {
        boolean monitoring = prefs.getBoolean(AlertStore.KEY_MONITORING, false);
        boolean stuck = monitoring && (!MonitorService.running || System.currentTimeMillis()
                - prefs.getLong(AlertStore.KEY_CHECK_TIME, 0) > STALE_MS);
        if (stuck) {
            prefs.edit().putLong(AlertStore.KEY_CHECK_TIME, System.currentTimeMillis())
                    .putString(AlertStore.KEY_STATUS, "Reiniciando monitoramento…").apply();
            startMonitor(MonitorService.ACTION_REFRESH);
        } else if (monitoring) {
            prefs.edit().putBoolean(AlertStore.KEY_MONITORING, false).apply();
            startService(new Intent(this, MonitorService.class).setAction(MonitorService.ACTION_STOP));
        } else {
            if (AlertStore.load(this).isEmpty()) {
                Toast.makeText(this, "Adicione um preço primeiro", Toast.LENGTH_SHORT).show();
                return;
            }
            prefs.edit().putBoolean(AlertStore.KEY_MONITORING, true)
                    .putLong(AlertStore.KEY_CHECK_TIME, System.currentTimeMillis())
                    .putString(AlertStore.KEY_STATUS, "Ligando monitoramento…").apply();
            // Sem essa permissão a notificação contínua e os avisos ficam invisíveis (Android 13+)
            requestNotificationsIfNeeded();
            startMonitor(null);
        }
        updateLiveFields();
    }

    private void startMonitor(String action) {
        Intent i = new Intent(this, MonitorService.class);
        if (action != null) i.setAction(action);
        try {
            startForegroundService(i);
        } catch (RuntimeException e) {
            prefs.edit().putBoolean(AlertStore.KEY_MONITORING, false).apply();
            Toast.makeText(this, "Não foi possível ligar o monitoramento", Toast.LENGTH_LONG).show();
        }
    }

    /** Pede ao serviço uma checagem imediata (ex.: mudou o horário) se ele estiver rodando. */
    private void nudgeMonitor() {
        if (MonitorService.running) {
            startService(new Intent(this, MonitorService.class).setAction(MonitorService.ACTION_REFRESH));
        }
    }

    private void pickTime(final String key, final Button target, final String prefix) {
        LocalTime t;
        try {
            t = LocalTime.parse(prefs.getString(key, "00:00"));
        } catch (Exception e) {
            t = LocalTime.MIDNIGHT;
        }
        new TimePickerDialog(this, new TimePickerDialog.OnTimeSetListener() {
            @Override public void onTimeSet(TimePicker view, int hour, int minute) {
                String v = LocalTime.of(hour, minute).format(CLOCK);
                prefs.edit().putString(key, v).apply();
                target.setText(prefix + v);
                nudgeMonitor();
            }
        }, t.getHour(), t.getMinute(), true).show();
    }

    private void pickSound() {
        Intent i = new Intent(RingtoneManager.ACTION_RINGTONE_PICKER);
        i.putExtra(RingtoneManager.EXTRA_RINGTONE_TYPE, RingtoneManager.TYPE_ALARM);
        i.putExtra(RingtoneManager.EXTRA_RINGTONE_TITLE, "Som do alerta BTC");
        i.putExtra(RingtoneManager.EXTRA_RINGTONE_SHOW_SILENT, false);
        i.putExtra(RingtoneManager.EXTRA_RINGTONE_SHOW_DEFAULT, true);
        String current = prefs.getString(AlertStore.KEY_SOUND, "");
        if (!current.isEmpty()) i.putExtra(RingtoneManager.EXTRA_RINGTONE_EXISTING_URI, Uri.parse(current));
        try {
            startActivityForResult(i, PICK_SOUND);
        } catch (RuntimeException e) {
            Toast.makeText(this, "Este celular não tem seletor de sons", Toast.LENGTH_LONG).show();
        }
    }

    @Override
    protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != PICK_SOUND || result != RESULT_OK || data == null) return;
        Uri uri = data.getParcelableExtra(RingtoneManager.EXTRA_RINGTONE_PICKED_URI);
        if (uri == null) return;
        String name = "Som escolhido";
        try {
            Ringtone r = RingtoneManager.getRingtone(this, uri);
            if (r != null) name = r.getTitle(this);
        } catch (Exception ignored) {
        }
        prefs.edit().putString(AlertStore.KEY_SOUND, uri.toString())
                .putString(AlertStore.KEY_SOUND_NAME, name).apply();
        soundText.setText(name);
    }

    private void requestNotificationsIfNeeded() {
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQUEST_NOTIFICATIONS);
        }
    }

    @Override
    public void onRequestPermissionsResult(int request, String[] perms, int[] results) {
        super.onRequestPermissionsResult(request, perms, results);
        if (request != REQUEST_NOTIFICATIONS) return;
        if (results.length == 0 || results[0] != PackageManager.PERMISSION_GRANTED) {
            prefs.edit().putBoolean(AlertStore.KEY_ALERT_NOTIFICATION, false).apply();
            if (notificationSwitch != null) notificationSwitch.setChecked(false);
            Toast.makeText(this, "Avisos na tela desligados. Som e vibração continuam disponíveis.", Toast.LENGTH_LONG).show();
        }
    }

    // ---------------------------------------------------------------- helpers

    private static String money(double v) {
        return "US" + NumberFormat.getCurrencyInstance(Locale.US).format(v);
    }

    private TextView text(String s, int sp, int color, boolean bold) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return t;
    }

    private Button button(String label, boolean primary) {
        Button b = new Button(this);
        b.setText(label);
        b.setTextSize(15);
        b.setAllCaps(false);
        b.setTextColor(primary ? Color.WHITE : BLUE);
        b.setBackground(shape(primary ? BLUE : SOFT_BLUE, 10));
        b.setStateListAnimator(null);
        b.setPadding(dp(14), 0, dp(14), 0);
        return b;
    }

    private GradientDrawable shape(int color, int radiusDp) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(color);
        d.setCornerRadius(dp(radiusDp));
        return d;
    }

    private LinearLayout card(LinearLayout parent) {
        LinearLayout c = vertical();
        c.setPadding(dp(16), dp(16), dp(16), dp(16));
        c.setBackground(shape(Color.WHITE, 16));
        c.setElevation(dp(2));
        parent.addView(c, new LinearLayout.LayoutParams(-1, -2));
        return c;
    }

    private void section(LinearLayout parent, String title) {
        gap(parent, 22);
        parent.addView(text(title, 18, INK, true));
        gap(parent, 10);
    }

    private LinearLayout vertical() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        return l;
    }

    private LinearLayout horizontal() {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.HORIZONTAL);
        return l;
    }

    private void gap(LinearLayout parent, int dp) {
        parent.addView(new View(this), new LinearLayout.LayoutParams(1, dp(dp)));
    }

    private void gapHorizontal(LinearLayout parent, int dp) {
        parent.addView(new View(this), new LinearLayout.LayoutParams(dp(dp), 1));
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }
}
