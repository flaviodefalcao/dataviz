package br.com.alertabt2;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.time.Instant;

final class PriceClient {
    static final String ENDPOINT = "https://api.exchange.coinbase.com/products/BTC-USD/ticker";
    private static final int MAX_BYTES = 64 * 1024;

    static final class Quote {
        final double price;
        final long timeMs;

        Quote(double price, long timeMs) {
            this.price = price;
            this.timeMs = timeMs;
        }
    }

    private PriceClient() {}

    /** Busca a cotação; tenta de novo uma vez em falha de rede. */
    static Quote fetchWithRetry() throws Exception {
        try {
            return fetch();
        } catch (IOException first) {
            Thread.sleep(1500);
            return fetch();
        }
    }

    static Quote fetch() throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(ENDPOINT).openConnection();
        c.setConnectTimeout(6000);
        c.setReadTimeout(6000);
        c.setUseCaches(false);
        c.setRequestProperty("Accept", "application/json");
        c.setRequestProperty("Cache-Control", "no-cache");
        c.setRequestProperty("User-Agent", "AlertaBTC/2.4");
        int code = c.getResponseCode();
        if (code != 200) {
            c.disconnect();
            throw new IOException("HTTP " + code);
        }
        ByteArrayOutputStream buf = new ByteArrayOutputStream(512);
        // Lê tudo e fecha o stream sem disconnect(): a conexão TLS volta ao pool (keep-alive)
        try (InputStream in = c.getInputStream()) {
            byte[] chunk = new byte[2048];
            int n;
            while ((n = in.read(chunk)) != -1) {
                buf.write(chunk, 0, n);
                if (buf.size() > MAX_BYTES) {
                    c.disconnect();
                    throw new IOException("Resposta muito grande");
                }
            }
        }
        JSONObject o = new JSONObject(new String(buf.toByteArray(), StandardCharsets.UTF_8));
        double price = Double.parseDouble(o.getString("price"));
        if (!(price > 0) || Double.isInfinite(price)) throw new IllegalStateException("Preço inválido");
        long time = Instant.parse(o.getString("time")).toEpochMilli();
        return new Quote(price, time);
    }
}
