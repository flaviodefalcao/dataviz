package br.com.alertabt2;

import java.time.LocalTime;

final class ThresholdEvaluator {
    static final long MAX_AGE_MS = 10 * 60_000L;
    static final long MAX_FUTURE_MS = 2 * 60_000L;

    private ThresholdEvaluator() {}

    /** true quando o preço está no lado "disparado" do limite. */
    static boolean condition(double price, double target, boolean above) {
        return above ? price >= target : price <= target;
    }

    /** Janela diária; início == fim significa dia inteiro; pode atravessar a meia-noite. */
    static boolean inWindow(LocalTime now, LocalTime start, LocalTime end) {
        if (start.equals(end)) return true;
        if (start.isBefore(end)) return !now.isBefore(start) && now.isBefore(end);
        return !now.isBefore(start) || now.isBefore(end);
    }

    static boolean isFresh(long tradeMs, long nowMs) {
        long age = nowMs - tradeMs;
        return age >= -MAX_FUTURE_MS && age <= MAX_AGE_MS;
    }
}
