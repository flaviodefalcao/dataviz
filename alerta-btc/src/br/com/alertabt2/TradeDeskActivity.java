package br.com.alertabt2;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Painel de análise (gráficos/indicadores) em WebView, a partir de assets/index.html. */
public final class TradeDeskActivity extends Activity {
    private static final int BG = Color.rgb(8, 14, 25);
    private WebView web;
    private final ExecutorService net = Executors.newFixedThreadPool(3);
    /** Únicos hosts que a página pode consultar pela ponte nativa (APIs públicas gratuitas). */
    private static final Set<String> ALLOWED = new HashSet<>(Arrays.asList(
            "fapi.binance.com", "www.okx.com", "api.alternative.me", "data-api.binance.vision"));
    private static final int MAX_BODY = 2 * 1024 * 1024;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        web = new WebView(this);
        web.setBackgroundColor(BG); // evita o "flash" branco ao abrir
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        // Segurança: a página só precisa de HTTPS público; sem acesso a arquivos locais.
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setAllowFileAccessFromFileURLs(false);
        s.setAllowUniversalAccessFromFileURLs(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setSupportZoom(false);
        // Só a página local é carregada: qualquer outro link é bloqueado (protege a ponte JS).
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                return !r.getUrl().toString().startsWith("file:///android_asset/");
            }
        });
        web.setWebChromeClient(new WebChromeClient()); // habilita alert()/confirm()
        web.addJavascriptInterface(new Bridge(), "Android");

        if (state != null) web.restoreState(state);
        else web.loadUrl("file:///android_asset/index.html");
    }

    /** Exposto ao JS como window.Android. */
    private final class Bridge {
        /** GET assíncrono sem restrição de CORS; responde em window.__nb(id, ok, corpo). */
        @JavascriptInterface
        public void get(final int id, final String url) {
            net.execute(new Runnable() {
                @Override public void run() {
                    boolean ok = false;
                    String body;
                    HttpURLConnection c = null;
                    try {
                        URL u = new URL(url);
                        if (!"https".equals(u.getProtocol()) || !ALLOWED.contains(u.getHost())) {
                            throw new SecurityException("host não permitido");
                        }
                        c = (HttpURLConnection) u.openConnection();
                        c.setConnectTimeout(8000);
                        c.setReadTimeout(8000);
                        c.setRequestProperty("Accept", "application/json");
                        c.setRequestProperty("User-Agent", "AlertaBTC/2.6");
                        int code = c.getResponseCode();
                        if (code != 200) throw new IllegalStateException("HTTP " + code);
                        ByteArrayOutputStream buf = new ByteArrayOutputStream();
                        try (InputStream in = c.getInputStream()) {
                            byte[] chunk = new byte[8192];
                            int n;
                            while ((n = in.read(chunk)) != -1) {
                                buf.write(chunk, 0, n);
                                if (buf.size() > MAX_BODY) throw new IllegalStateException("resposta grande demais");
                            }
                        }
                        body = new String(buf.toByteArray(), StandardCharsets.UTF_8);
                        ok = true;
                    } catch (Exception e) {
                        body = e.getClass().getSimpleName() + ": " + e.getMessage();
                        if (c != null) c.disconnect();
                    }
                    final String js = "window.__nb&&window.__nb(" + id + "," + ok + "," + JSONObject.quote(body) + ")";
                    runOnUiThread(new Runnable() {
                        @Override public void run() {
                            if (web != null) web.evaluateJavascript(js, null);
                        }
                    });
                }
            });
        }

        @JavascriptInterface
        public void share(final String fileName, final String text) {
            runOnUiThread(new Runnable() {
                @Override public void run() {
                    Intent send = new Intent(Intent.ACTION_SEND)
                            .setType("text/plain")
                            .putExtra(Intent.EXTRA_SUBJECT, fileName)
                            .putExtra(Intent.EXTRA_TEXT, text);
                    try {
                        startActivity(Intent.createChooser(send, "Exportar histórico"));
                    } catch (RuntimeException ignored) {
                    }
                }
            });
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        if (web != null) web.saveState(out);
    }

    // Pausa JS/timers/WebSocket em segundo plano: poupa bateria e dados.
    @Override
    protected void onPause() {
        if (web != null) {
            web.onPause();
            web.pauseTimers();
        }
        super.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (web != null) {
            web.resumeTimers();
            web.onResume();
        }
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        net.shutdownNow();
        if (web != null) {
            web.stopLoading();
            web.destroy();
            web = null;
        }
        super.onDestroy();
    }
}
