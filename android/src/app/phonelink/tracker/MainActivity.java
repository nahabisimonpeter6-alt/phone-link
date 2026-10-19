package app.phonelink.tracker;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.location.LocationManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import org.json.JSONObject;
import java.text.DateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private final int GREEN = Color.rgb(24, 63, 53), MUTED = Color.rgb(113, 128, 120);
    private SharedPreferences prefs;
    private LinearLayout root;
    private EditText serverField, codeField;
    private TextView status, detail, error;
    private Button start, stop, connect;
    private final ExecutorService network = Executors.newSingleThreadExecutor();
    private final Handler handler = new Handler(Looper.getMainLooper());
    private boolean showingPaired;
    private final Runnable refresh = new Runnable() {
        @Override public void run() {
            boolean paired = prefs.contains("token");
            if (paired != showingPaired) render();
            updateStatus(); handler.postDelayed(this, 2000);
        }
    };

    @Override public void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        prefs = getSharedPreferences("phonelink", MODE_PRIVATE);
        // Persisted flags can survive a force-stop or Android's Task Manager stop.
        // A fresh process must still offer Start instead of pretending to share.
        if (!TrackingService.active) prefs.edit().putBoolean("running", false).putBoolean("stopping", false).apply();
        render();
    }

    @Override protected void onResume() { super.onResume(); handler.post(refresh); }
    @Override protected void onPause() { super.onPause(); handler.removeCallbacks(refresh); }
    @Override protected void onDestroy() { handler.removeCallbacksAndMessages(null); network.shutdown(); super.onDestroy(); }

    private int dp(int value) { return (int) (getResources().getDisplayMetrics().density * value + .5f); }
    private GradientDrawable background(int color, int radius, boolean border) {
        GradientDrawable shape = new GradientDrawable(); shape.setColor(color); shape.setCornerRadius(dp(radius));
        if (border) shape.setStroke(dp(1), Color.rgb(223, 228, 217)); return shape;
    }
    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(color);
        view.setLineSpacing(dp(3), 1); if (bold) view.setTypeface(null, Typeface.BOLD);
        return view;
    }
    private void add(View view, int top) {
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2); p.topMargin = dp(top); root.addView(view, p);
    }
    private Button button(String value, boolean primary) {
        Button view = new Button(this); view.setText(value); view.setAllCaps(false); view.setTextSize(14);
        view.setTextColor(primary ? Color.WHITE : GREEN); view.setMinHeight(dp(52));
        view.setBackground(background(primary ? GREEN : Color.rgb(235, 240, 225), 9, false));
        view.setPadding(dp(16), dp(10), dp(16), dp(10)); return view;
    }
    private EditText input(String hint, int type) {
        EditText view = new EditText(this); view.setSingleLine(true); view.setHint(hint); view.setTextSize(14); view.setTextColor(GREEN);
        view.setInputType(type); view.setPadding(dp(14), dp(15), dp(14), dp(15));
        view.setBackground(background(Color.WHITE, 8, true)); return view;
    }

    private void render() {
        showingPaired = prefs.contains("token");
        ScrollView scroll = new ScrollView(this); scroll.setFillViewport(true); scroll.setBackgroundColor(Color.rgb(246, 246, 240));
        root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setPadding(dp(26), dp(24), dp(26), dp(32));
        scroll.addView(root); setContentView(scroll);
        // Target 35 uses edge-to-edge on Android 15; keep every control clear of system bars.
        scroll.setOnApplyWindowInsetsListener((view, insets) -> {
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            } else view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(), insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets;
        });
        scroll.requestApplyInsets();
        add(text("⌖  PhoneLink.", 26, GREEN, true), 0);
        add(text("YOUR PHONE, CONNECTED", 10, MUTED, true), 42);
        add(text(showingPaired ? "A little peace\nof mind." : "Find your\nway back.", 38, GREEN, false), 16);
        add(text(showingPaired ? "Your phone is paired. You control when its location is shared." : "Connect this phone to your private dashboard. You’ll need a pairing code from the website.", 14, MUTED, false), 16);
        error = text("", 13, Color.rgb(161, 57, 43), false);
        if (!showingPaired) renderPair(); else renderTracker();
        add(error, 16);
        add(text("Location sharing uses battery and an internet connection. When the phone cannot send updates, the dashboard shows its last known location.", 12, MUTED, false), 32);
    }

    private void renderPair() {
        error.setText(prefs.getString("last_error", ""));
        add(text("Server address", 12, GREEN, true), 32);
        serverField = input("https://yourname.pythonanywhere.com", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        serverField.setText(prefs.getString("server", "")); add(serverField, 9);
        add(text("Enter the hosted website’s HTTPS address. For local testing, use your computer’s Wi-Fi IP, such as http://192.168.1.10:8080, on the same Wi-Fi. Localhost points to this phone and will not reach your computer. Paste only the address, without spaces or link text.", 11, MUTED, false), 8);
        add(text("Pairing code", 12, GREEN, true), 24);
        codeField = input("ABCD-EFGH-JKLM", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        add(codeField, 9);
        connect = button("Connect phone  ↗", true); add(connect, 24);
        connect.setOnClickListener(view -> pair());
    }

    private void pair() {
        final String address;
        try { address = ApiClient.normalizeServer(serverField.getText().toString()); }
        catch (Exception ex) { error.setText(ex.getMessage()); return; }
        serverField.setText(address);
        final String code = codeField.getText().toString().trim();
        if (code.isEmpty()) { error.setText("Enter the pairing code from your dashboard."); return; }
        connect.setEnabled(false); error.setText("Connecting…");
        network.execute(() -> {
            try {
                JSONObject body = new JSONObject(); body.put("code", code);
                JSONObject response = ApiClient.post(address, "/api/pair", null, body);
                prefs.edit().putString("server", address).putString("token", response.getString("device_token"))
                    .putString("name", response.getString("name")).putBoolean("running", false).remove("last_error")
                    .remove("last_sent").remove("fix_time").remove("fix_lat").remove("fix_lng").remove("fix_accuracy").apply();
                runOnUiThread(() -> { if (!isFinishing() && !isDestroyed()) render(); });
            } catch (Exception ex) {
                runOnUiThread(() -> {
                    if (isFinishing() || isDestroyed()) return;
                    connect.setEnabled(true);
                    error.setText(ex instanceof ApiClient.ApiException ? ex.getMessage() : "Cannot reach the server. Open the same address in this phone’s browser first. For local testing, keep the computer’s server running and both devices on the same Wi-Fi. For hosting, check that the HTTPS website is online.");
                });
            }
        });
    }

    private void renderTracker() {
        add(text(prefs.getString("name", "My phone"), 22, GREEN, true), 30);
        add(text(prefs.getString("server", ""), 12, MUTED, false), 4);
        status = text("Sharing is stopped", 18, GREEN, true); add(status, 26);
        detail = text("", 12, MUTED, false); add(detail, 9);
        start = button("Start tracking  ↗", true); add(start, 22); start.setOnClickListener(view -> requestStart());
        stop = button("Stop tracking", false); add(stop, 12); stop.setOnClickListener(view -> {
            stop.setEnabled(false);
            startService(new Intent(this, TrackingService.class).setAction(TrackingService.STOP));
            handler.postDelayed(this::updateStatus, 200);
        });
        Button settings = button("Location settings", false); add(settings, 12);
        settings.setOnClickListener(view -> startActivity(new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS)));
        Button disconnect = button("Unpair this app", false); add(disconnect, 12);
        disconnect.setOnClickListener(view -> new AlertDialog.Builder(this).setTitle("Unpair this phone?")
            .setMessage("Tracking will stop. Remove the phone from the dashboard too if you want to delete its saved location.")
            .setNegativeButton("Keep connected", null).setPositiveButton("Unpair", (dialog, which) -> {
                // The service captures its credentials before local credentials are removed.
                prefs.edit().putBoolean("unpair_requested", true).apply();
                startService(new Intent(this, TrackingService.class).setAction(TrackingService.STOP));
                handler.postDelayed(() -> { if (!isDestroyed()) render(); }, 300);
            }).show());
        add(text("A tracking notification stays visible while sharing is active. Start sharing before the phone goes missing. After a restart or force-stop, open this app and start again.", 12, MUTED, false), 24);
        updateStatus();
    }

    private void requestStart() {
        ArrayList<String> missing = new ArrayList<>();
        if (checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            missing.add(Manifest.permission.ACCESS_FINE_LOCATION); missing.add(Manifest.permission.ACCESS_COARSE_LOCATION);
        }
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            missing.add(Manifest.permission.POST_NOTIFICATIONS);
        if (!missing.isEmpty()) {
            new AlertDialog.Builder(this).setTitle("Share this phone’s location?")
                .setMessage("PhoneLink sends this phone’s location to your paired dashboard about every 15 seconds, including while the screen is locked. Choose Precise location for the best result. You can stop sharing in the app or notification.")
                .setNegativeButton("Cancel", null).setPositiveButton("Continue", (d, w) -> requestPermissions(missing.toArray(new String[0]), 10)).show();
        } else startTracking();
    }

    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == 10) {
            if (checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED) startTracking();
            else error.setText("Location permission is needed to share a location. You can allow it in Android Settings → Apps → PhoneLink → Permissions.");
        }
    }

    private void startTracking() {
        LocationManager manager = (LocationManager) getSystemService(LOCATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 28 && !manager.isLocationEnabled()) {
            error.setText("Turn on your phone’s location, then tap Start tracking."); return;
        }
        try {
            error.setText("");
            startForegroundService(new Intent(this, TrackingService.class));
            handler.postDelayed(this::updateStatus, 300);
        } catch (Exception ex) { error.setText("Android could not start tracking. Keep the app open and try again."); }
    }

    private void updateStatus() {
        if (!showingPaired || status == null) return;
        boolean running = prefs.getBoolean("running", false);
        boolean stopping = prefs.getBoolean("stopping", false);
        status.setText(stopping ? "Stopping sharing…" : running ? "●  Location sharing is active" : "Sharing is stopped");
        long sent = prefs.getLong("last_sent", 0);
        String info = sent == 0 ? "No report sent yet." : "Last report sent: " + DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.MEDIUM).format(new Date(sent));
        long fix = prefs.getLong("fix_time", 0);
        if (fix > 0) info += "\nLocation accuracy: ± " + Math.round(prefs.getFloat("fix_accuracy", 0)) + " m";
        else if (running) info += "\nWaiting for a location fix. Try near a window or outdoors.";
        detail.setText(info); error.setText(prefs.getString("last_error", ""));
        start.setEnabled(!running && !stopping); stop.setEnabled(running && !stopping);
    }
}
