package br.com.alertabt2;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

final class AlertStore {
    static final String PREFS = "btc_alert_settings";
    static final String KEY_ALERTS = "alerts";
    static final String KEY_ALERT_NOTIFICATION = "alert_notification";
    static final String KEY_CHECK_TIME = "last_check_time";
    static final String KEY_END = "window_end";
    static final String KEY_MONITORING = "monitoring";
    static final String KEY_PRICE = "last_price";
    static final String KEY_SOUND = "sound_uri";
    static final String KEY_SOUND_ENABLED = "sound_enabled";
    static final String KEY_SOUND_NAME = "sound_name";
    static final String KEY_START = "window_start";
    static final String KEY_STATUS = "status";
    static final String KEY_TRADE_TIME = "last_trade_time";
    static final String KEY_VIBRATE = "vibrate";
    static final String KEY_WINDOW = "window_enabled";
    static final String KEY_WIDGET_ERROR = "widget_error";

    static final class Alert {
        final long id;
        final double target;
        final boolean above;
        boolean armed;

        Alert(long id, double target, boolean above, boolean armed) {
            this.id = id;
            this.target = target;
            this.above = above;
            this.armed = armed;
        }
    }

    private AlertStore() {}

    static SharedPreferences prefs(Context c) {
        return c.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static List<Alert> load(Context c) {
        List<Alert> out = new ArrayList<>();
        try {
            JSONArray arr = new JSONArray(prefs(c).getString(KEY_ALERTS, "[]"));
            for (int i = 0; i < arr.length(); i++) {
                JSONObject o = arr.getJSONObject(i);
                out.add(new Alert(o.getLong("id"), o.getDouble("target"),
                        o.getBoolean("above"), o.optBoolean("armed", true)));
            }
        } catch (Exception ignored) {
            // dados corrompidos: devolve o que conseguiu ler
        }
        return out;
    }

    static void save(Context c, List<Alert> alerts) {
        JSONArray arr = new JSONArray();
        try {
            for (Alert a : alerts) {
                JSONObject o = new JSONObject();
                o.put("id", a.id);
                o.put("target", a.target);
                o.put("above", a.above);
                o.put("armed", a.armed);
                arr.put(o);
            }
        } catch (Exception ignored) {
        }
        prefs(c).edit().putString(KEY_ALERTS, arr.toString()).apply();
    }

    static void saveQuote(Context c, PriceClient.Quote q) {
        prefs(c).edit()
                .putLong(KEY_PRICE, Double.doubleToRawLongBits(q.price))
                .putLong(KEY_TRADE_TIME, q.timeMs)
                .putBoolean(KEY_WIDGET_ERROR, false)
                .apply();
    }

    static double lastPrice(SharedPreferences p) {
        return Double.longBitsToDouble(p.getLong(KEY_PRICE, 0L));
    }
}
