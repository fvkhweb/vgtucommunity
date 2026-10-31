package com.example.schedule

import android.annotation.SuppressLint
import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Bundle
import android.view.KeyEvent
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    private lateinit var webView: WebView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        webView = WebView(this)
        webView.layoutParams = android.view.ViewGroup.LayoutParams(
            android.view.ViewGroup.LayoutParams.MATCH_PARENT,
            android.view.ViewGroup.LayoutParams.MATCH_PARENT
        )
        setContentView(webView)

        val settings: WebSettings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.allowFileAccess = true
        settings.allowContentAccess = true
        settings.allowFileAccessFromFileURLs = true
        settings.allowUniversalAccessFromFileURLs = true
        settings.databaseEnabled = true
        settings.cacheMode = WebSettings.LOAD_DEFAULT
        settings.setSupportZoom(false)
        settings.builtInZoomControls = false
        settings.displayZoomControls = false

        webView.setBackgroundColor(android.graphics.Color.parseColor("#0f1115"))
        val handler = android.os.Handler(android.os.Looper.getMainLooper())
        val fallback = Runnable {
            if (webView.url?.startsWith("https://") == true) {
                webView.loadUrl("file:///android_asset/index.html")
            }
        }
        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                handler.removeCallbacks(fallback)
                // Если есть сеть — подтягиваем свежее расписание поверх локального
                if (isOnline() && url?.startsWith("file://") == true) {
                    view?.evaluateJavascript("""
                        (function(){
                            try {
                                fetch('https://vgtucommunity.2bd.net/schedule.json', {cache:'no-store'})
                                    .then(function(r){ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
                                    .then(function(d){ if (typeof applyScheduleData === 'function') applyScheduleData(d); })
                                    .catch(function(e){});
                            } catch(e) {}
                        })();
                    """.trimIndent(), null)
                }
            }
            override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                handler.removeCallbacks(fallback)
                if (view?.url?.startsWith("https://") == true) {
                    view.loadUrl("file:///android_asset/index.html")
                }
            }
        }
        webView.webChromeClient = WebChromeClient()

        webView.loadUrl("file:///android_asset/index.html")
    }

    private fun isOnline(): Boolean {
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val net = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(net) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK && webView.canGoBack()) {
            webView.goBack()
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onDestroy() {
        webView.destroy()
        super.onDestroy()
    }
}