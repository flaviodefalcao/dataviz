package br.com.alertabt2;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.widget.RemoteViews;

import java.text.NumberFormat;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;

public final class BtcWidgetProvider extends AppWidgetProvider {
    private static final String REFRESH = "br.com.alertabt2.WIDGET_REFRESH";
    private static final AtomicBoolean FETCHING = new AtomicBoolean(false);
    private static final int COLOR_WARN = 0xFFF6B84C;
    private static final int COLOR_OK = 0xFFA8B8CF;
    /** Se o monitor buscou há menos que isso, o widget só redesenha, sem nova requisição. */
    private static final long REUSE_MS = 45_000;

    /** Redesenha o widget a partir da última cotação salva (sem rede). */
    public static void updateAll(Context context) {
        try {
            AppWidgetManager mgr = AppWidgetManager.getInstance(context);
            int[] ids = mgr.getAppWidgetIds(new ComponentName(context, BtcWidgetProvider.class));
            if (ids == null || ids.length == 0) return;

            SharedPreferences p = AlertStore.prefs(context);
            double price = AlertStore.lastPrice(p);
            long trade = p.getLong(AlertStore.KEY_TRADE_TIME, 0);
            boolean hasQuote = price > 0 && !Double.isInfinite(price) && trade > 0;
            boolean stale = !ThresholdEvaluator.isFresh(trade, System.currentTimeMillis());
            boolean error = p.getBoolean(AlertStore.KEY_WIDGET_ERROR, false);

            String priceText;
            String timeText;
            if (hasQuote) {
                NumberFormat nf = NumberFormat.getNumberInstance(Locale.US);
                nf.setMinimumFractionDigits(2);
                nf.setMaximumFractionDigits(2);
                priceText = "US$ " + nf.format(price);
                String when = new SimpleDateFormat("dd/MM HH:mm", new Locale("pt", "BR")).format(new Date(trade));
                timeText = (error ? "Falha ao atualizar · " : stale ? "Desatualizado · " : "Cotação · ") + when;
            } else {
                priceText = "US$ —";
                timeText = error ? "Falha · toque em atualizar" : "Toque em atualizar";
            }

            RemoteViews v = new RemoteViews(context.getPackageName(), R.layout.btc_widget);
            v.setTextViewText(R.id.widget_price, priceText);
            v.setTextViewText(R.id.widget_time, timeText);
            v.setTextColor(R.id.widget_time, (!hasQuote || error || stale) ? COLOR_WARN : COLOR_OK);

            Intent open = new Intent(context, MainActivity.class)
                    .setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
            PendingIntent openPi = PendingIntent.getActivity(context, 141, open,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            v.setOnClickPendingIntent(R.id.widget_root, openPi);
            v.setOnClickPendingIntent(R.id.widget_price, openPi);
            PendingIntent refreshPi = PendingIntent.getBroadcast(context, 142,
                    new Intent(context, BtcWidgetProvider.class).setAction(REFRESH),
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            v.setOnClickPendingIntent(R.id.widget_refresh, refreshPi);
            mgr.updateAppWidget(ids, v);
        } catch (RuntimeException ignored) {
        }
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent != null ? intent.getAction() : null;
        if (!REFRESH.equals(action) && !AppWidgetManager.ACTION_APPWIDGET_UPDATE.equals(action)) {
            super.onReceive(context, intent);
            return;
        }
        updateAll(context);

        // O monitor já está buscando a cada minuto: evita requisição duplicada.
        SharedPreferences p = AlertStore.prefs(context);
        boolean recent = System.currentTimeMillis() - p.getLong(AlertStore.KEY_CHECK_TIME, 0) < REUSE_MS;
        if (!REFRESH.equals(action) && MonitorService.running && recent) return;

        if (!FETCHING.compareAndSet(false, true)) return;
        final Context app = context.getApplicationContext();
        final BroadcastReceiver.PendingResult pending = goAsync();
        new Thread(new Runnable() {
            @Override public void run() {
                try {
                    PriceClient.Quote q = PriceClient.fetch(); // sem retry: goAsync tem ~10 s
                    if (!ThresholdEvaluator.isFresh(q.timeMs, System.currentTimeMillis())) {
                        throw new IllegalStateException("Cotação antiga");
                    }
                    AlertStore.saveQuote(app, q);
                } catch (Exception e) {
                    AlertStore.prefs(app).edit().putBoolean(AlertStore.KEY_WIDGET_ERROR, true).apply();
                } finally {
                    updateAll(app);
                    FETCHING.set(false);
                    pending.finish();
                }
            }
        }, "BTC-widget-refresh").start();
    }

    @Override
    public void onUpdate(Context context, AppWidgetManager mgr, int[] ids) {
        updateAll(context);
    }

    @Override
    public void onAppWidgetOptionsChanged(Context context, AppWidgetManager mgr, int id, Bundle options) {
        updateAll(context);
    }
}
