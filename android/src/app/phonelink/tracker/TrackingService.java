package app.phonelink.tracker;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.BatteryManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import org.json.JSONObject;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class TrackingService extends Service implements LocationListener {
    static volatile boolean active = false;
    static final String STOP = "app.phonelink.tracker.STOP";
    private SharedPreferences prefs;
    private LocationManager locations;
    private volatile Location latest;
    private ScheduledExecutorService network;
    private ScheduledFuture<?> reportTask;
    private String server, token;
    private boolean started = false;
    private volatile boolean stopping = false;

    @Override public void onCreate() {
        super.onCreate();
        prefs = getSharedPreferences("phonelink", MODE_PRIVATE);
        prefs.edit().putBoolean("stopping", false).apply();
        server = prefs.getString("server", ""); token = prefs.getString("token", "");
        locations = (LocationManager) getSystemService(LOCATION_SERVICE);
        network = Executors.newSingleThreadScheduledExecutor();
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && STOP.equals(intent.getAction())) { stopSharing(); return START_NOT_STICKY; }
        if (started) return START_STICKY;
        if (token.isEmpty() || checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            prefs.edit().putBoolean("running", false).putString("last_error", "Allow location permission, then tap Start tracking.").apply();
            stopSelf(); return START_NOT_STICKY;
        }
        try {
            showNotification();
            loadCachedFix();
            int providers = 0;
            if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED && locations.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
                locations.requestLocationUpdates(LocationManager.GPS_PROVIDER, 15000, 0, this, Looper.getMainLooper()); providers++;
                consider(locations.getLastKnownLocation(LocationManager.GPS_PROVIDER));
            }
            if (locations.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
                locations.requestLocationUpdates(LocationManager.NETWORK_PROVIDER, 15000, 0, this, Looper.getMainLooper()); providers++;
                consider(locations.getLastKnownLocation(LocationManager.NETWORK_PROVIDER));
            }
            if (providers == 0) throw new Exception("No location provider is available. Enable phone location and grant Precise location permission.");
            started = true;
            active = true;
            prefs.edit().putBoolean("running", true).remove("last_error").apply();
            reportTask = network.scheduleWithFixedDelay(() -> sendReport(true), 0, 15, TimeUnit.SECONDS);
            return START_STICKY;
        } catch (Exception ex) {
            prefs.edit().putBoolean("running", false).putString("last_error", ex.getMessage() == null ? "Cannot start location sharing. Check location permission and settings." : ex.getMessage()).apply();
            stopSelf(); return START_NOT_STICKY;
        }
    }

    private void showNotification() {
        NotificationManager manager = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        manager.createNotificationChannel(new NotificationChannel("tracking", "Location sharing", NotificationManager.IMPORTANCE_LOW));
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent stop = PendingIntent.getService(this, 1, new Intent(this, TrackingService.class).setAction(STOP), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification notification = new Notification.Builder(this, "tracking").setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("PhoneLink · Location sharing is active")
            .setContentText("Your paired dashboard receives this phone’s location.")
            .setContentIntent(open).setOngoing(true).setCategory(Notification.CATEGORY_SERVICE)
            .addAction(new Notification.Action.Builder(null, "Stop sharing", stop).build()).build();
        if (Build.VERSION.SDK_INT >= 29) startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION);
        else startForeground(1, notification);
    }

    private void loadCachedFix() {
        if (!prefs.contains("fix_time")) return;
        Location cached = new Location("cached");
        cached.setLatitude(Double.longBitsToDouble(prefs.getLong("fix_lat", 0)));
        cached.setLongitude(Double.longBitsToDouble(prefs.getLong("fix_lng", 0)));
        cached.setAccuracy(prefs.getFloat("fix_accuracy", 0)); cached.setTime(prefs.getLong("fix_time", 0)); latest = cached;
    }

    private synchronized void consider(Location location) {
        if (location == null || !location.hasAccuracy()) return;
        Location previous = latest;
        if (previous != null && location.getTime() < previous.getTime()) return;
        // Do not let a coarse network fix replace a recent, precise GPS fix.
        if (previous != null && location.getTime() - previous.getTime() < 30000 && location.getAccuracy() > previous.getAccuracy() * 2) return;
        latest = new Location(location);
        prefs.edit().putLong("fix_lat", Double.doubleToLongBits(location.getLatitude())).putLong("fix_lng", Double.doubleToLongBits(location.getLongitude()))
            .putFloat("fix_accuracy", location.getAccuracy()).putLong("fix_time", location.getTime()).apply();
    }

    @Override public void onLocationChanged(Location location) { consider(location); }
    @Override public void onProviderDisabled(String provider) {
        prefs.edit().putString("last_error", "A location provider was disabled. Keep phone location enabled; the dashboard retains your last known position.").apply();
    }
    @Override public void onProviderEnabled(String provider) { prefs.edit().remove("last_error").apply(); }
    @Override public void onStatusChanged(String provider, int status, Bundle extras) { }

    private void sendReport(boolean tracking) {
        if (tracking && stopping) return;
        try {
            JSONObject body = new JSONObject(); body.put("tracking", tracking);
            BatteryManager battery = (BatteryManager) getSystemService(BATTERY_SERVICE);
            int percent = battery.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY);
            if (percent >= 0 && percent <= 100) body.put("battery", percent);
            Location fix = latest;
            if (fix != null) {
                JSONObject loc = new JSONObject(); loc.put("latitude", fix.getLatitude()); loc.put("longitude", fix.getLongitude());
                loc.put("accuracy", fix.getAccuracy()); loc.put("timestamp", fix.getTime() / 1000.0); body.put("location", loc);
            }
            ApiClient.post(server, "/api/report", token, body);
            prefs.edit().putLong("last_sent", System.currentTimeMillis()).remove("last_error").apply();
        } catch (ApiClient.ApiException ex) {
            prefs.edit().putString("last_error", ex.getMessage()).apply();
            if (ex.status == 401) {
                prefs.edit().remove("token").putBoolean("running", false).apply();
                new Handler(Looper.getMainLooper()).post(() -> { stopping = true; stopSelf(); });
            }
        } catch (Exception ex) {
            prefs.edit().putString("last_error", "Cannot reach the server. Keeping the latest fix and retrying automatically. Check internet access and the server address.").apply();
        }
    }

    private void stopSharing() {
        if (stopping) return;
        stopping = true;
        prefs.edit().putBoolean("running", false).putBoolean("stopping", true).apply();
        locations.removeUpdates(this);
        // Serialize the final report after any in-flight report so that an older
        // "tracking=true" request cannot overwrite the stopped state.
        if (reportTask != null) reportTask.cancel(false);
        network.execute(() -> {
            try { if (!token.isEmpty()) sendReport(false); }
            finally {
                if (prefs.getBoolean("unpair_requested", false)) {
                    prefs.edit().remove("token").remove("name").remove("last_sent").remove("fix_time").remove("fix_lat").remove("fix_lng")
                        .remove("fix_accuracy").remove("last_error").remove("unpair_requested").apply();
                }
                new Handler(Looper.getMainLooper()).post(this::stopSelf);
            }
        });
        network.shutdown();
    }

    @Override public void onDestroy() {
        active = false;
        stopping = true;
        locations.removeUpdates(this);
        network.shutdownNow();
        prefs.edit().putBoolean("running", false).putBoolean("stopping", false).apply();
        stopForeground(STOP_FOREGROUND_REMOVE);
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent intent) { return null; }
}
