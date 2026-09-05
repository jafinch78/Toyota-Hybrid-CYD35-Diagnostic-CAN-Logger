package com.jafinch78.toyotacansync;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.View;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;

public class MainActivity extends Activity implements BleSyncManager.Listener {
    private static final int PERMISSION_REQUEST = 100;
    private static final int PROJECTION_REQUEST = 101;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private BleSyncManager ble;
    private TextView statusText;
    private Button startButton;
    private Button markerButton;
    private Button stopButton;
    private Button shareButton;
    private boolean capturing;
    private boolean stopPending;
    private int markerNumber = 1;

    private final Runnable periodicSync = new Runnable() {
        @Override public void run() {
            if (!capturing) return;
            runSyncBurst(5, 120, null);
            handler.postDelayed(this, 30_000);
        }
    };

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        statusText = findViewById(R.id.statusText);
        startButton = findViewById(R.id.startButton);
        markerButton = findViewById(R.id.markerButton);
        stopButton = findViewById(R.id.stopButton);
        shareButton = findViewById(R.id.shareButton);
        ble = new BleSyncManager(this, this);

        findViewById(R.id.permissionButton).setOnClickListener(v -> requestRequiredPermissions());
        findViewById(R.id.connectButton).setOnClickListener(v -> {
            if (!hasRequiredPermissions()) requestRequiredPermissions();
            else ble.scanAndConnect();
        });
        startButton.setOnClickListener(v -> beginSyncedCapture());
        markerButton.setOnClickListener(v -> addMarker());
        stopButton.setOnClickListener(v -> finishSyncedCapture());
        shareButton.setOnClickListener(v -> shareCapture());
    }

    private void beginSyncedCapture() {
        if (!ble.isReady() || capturing) return;
        new AlertDialog.Builder(this)
                .setTitle("Confirm OBD reader app")
                .setMessage("Before recording, confirm Hybrid Assistant, Dr. Prius, Autel, or the other OBD reader app has been opened and connected to its adapter. Return here, then continue.")
                .setPositiveButton("CONTINUE", (dialog, which) -> beginSyncedCaptureAfterConfirmation())
                .setNegativeButton("NOT YET", null)
                .show();
    }

    private void beginSyncedCaptureAfterConfirmation() {
        if (!ble.isReady() || capturing) return;
        try {
            SyncStore.begin(this);
            SyncStore.setBleDevice(ble.deviceName(), ble.deviceAddress());
        } catch (Exception error) {
            setStatus("Cannot create capture: " + error.getMessage());
            return;
        }
        startButton.setEnabled(false);
        setStatus("Collecting pre-capture BLE clock samples...");
        runSyncBurst(15, 100, () -> {
            MediaProjectionManager manager = (MediaProjectionManager)
                    getSystemService(Context.MEDIA_PROJECTION_SERVICE);
            startActivityForResult(manager.createScreenCaptureIntent(), PROJECTION_REQUEST);
        });
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PROJECTION_REQUEST) return;
        if (resultCode != RESULT_OK || data == null) {
            setStatus("Screen recording was not authorized.");
            startButton.setEnabled(ble.isReady());
            return;
        }
        Intent service = new Intent(this, CaptureService.class);
        service.setAction(CaptureService.ACTION_START);
        service.putExtra(CaptureService.EXTRA_RESULT_CODE, resultCode);
        service.putExtra(CaptureService.EXTRA_RESULT_DATA, data);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(service);
        } else {
            // Android 6.0/API 23 through Android 7.x do not have
            // startForegroundService(). CaptureService immediately promotes
            // itself with startForeground(), so startService() is correct here.
            startService(service);
        }
        capturing = true;
        markerButton.setEnabled(true);
        stopButton.setEnabled(true);
        ble.sendControl("START_PASSIVE", 1, 0);
        handler.postDelayed(() -> runSyncBurst(15, 100, null), 300);
        handler.removeCallbacks(periodicSync);
        handler.postDelayed(periodicSync, 30_000);
        setStatus("Recording. Switch to the diagnostic app and narrate observations.");
    }

    private void addMarker() {
        if (!capturing) return;
        int marker = markerNumber++;
        SyncStore.addLocalMarker(marker, SystemClock.elapsedRealtimeNanos());
        ble.sendControl("MARKER", 3, marker);
        setStatus("Marker " + marker + " recorded. Speak the observation now.");
    }

    private void finishSyncedCapture() {
        if (!capturing) return;
        stopButton.setEnabled(false);
        markerButton.setEnabled(false);
        handler.removeCallbacks(periodicSync);
        setStatus("Collecting final clock samples and closing both recordings...");
        runSyncBurst(15, 100, () -> {
            stopPending = true;
            ble.sendControl("STOP", 2, 0);
            // Fallback prevents an endless recording if the BLE acknowledgement
            // is lost after the CYD has already closed its files.
            handler.postDelayed(() -> { if (stopPending) completeLocalStop(); }, 5_000);
        });
    }

    private void completeLocalStop() {
        if (!capturing) return;
        stopPending = false;
        Intent stop = new Intent(this, CaptureService.class);
        stop.setAction(CaptureService.ACTION_STOP);
        startService(stop);
        capturing = false;
        startButton.setEnabled(ble.isReady());
        handler.postDelayed(() -> shareButton.setEnabled(true), 500);
        setStatus("Capture closed. Share its ZIP or copy it to the Windows processor.");
    }

    private void runSyncBurst(int count, long intervalMs, Runnable finished) {
        runSyncBurstStep(count, intervalMs, finished);
    }

    private void runSyncBurstStep(int remaining, long intervalMs, Runnable finished) {
        if (remaining <= 0) {
            if (finished != null) finished.run();
            return;
        }
        ble.sendTimeProbe();
        handler.postDelayed(() -> runSyncBurstStep(remaining - 1, intervalMs, finished), intervalMs);
    }

    private void shareCapture() {
        try {
            SyncStore.shareLast(this);
        } catch (Exception error) {
            Toast.makeText(this, "Share failed: " + error.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    private List<String> requiredPermissions() {
        List<String> result = new ArrayList<>();
        result.add(Manifest.permission.RECORD_AUDIO);
        if (Build.VERSION.SDK_INT >= 31) {
            result.add(Manifest.permission.BLUETOOTH_SCAN);
            result.add(Manifest.permission.BLUETOOTH_CONNECT);
        } else {
            result.add(Manifest.permission.ACCESS_FINE_LOCATION);
        }
        if (Build.VERSION.SDK_INT >= 33) result.add(Manifest.permission.POST_NOTIFICATIONS);
        return result;
    }

    private boolean hasRequiredPermissions() {
        for (String permission : requiredPermissions())
            if (checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED) return false;
        return true;
    }

    private void requestRequiredPermissions() {
        List<String> missing = new ArrayList<>();
        for (String permission : requiredPermissions())
            if (checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED) missing.add(permission);
        if (missing.isEmpty()) setStatus("Permissions granted. Connect to ToyotaCYD.");
        else requestPermissions(missing.toArray(new String[0]), PERMISSION_REQUEST);
    }

    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (requestCode == PERMISSION_REQUEST)
            setStatus(hasRequiredPermissions() ? "Permissions granted. Connect to ToyotaCYD."
                    : "One or more required permissions were denied.");
    }

    private void setStatus(String status) { statusText.setText(status); }

    @Override public void onStatus(String status) { runOnUiThread(() -> setStatus(status)); }

    @Override public void onReady(String name, String address) {
        runOnUiThread(() -> {
            setStatus("Connected to " + name + " (" + address + ").");
            startButton.setEnabled(!capturing);
        });
    }

    @Override public void onDisconnected() {
        runOnUiThread(() -> {
            setStatus("ToyotaCYD BLE disconnected. Video continues, but resynchronize before another capture.");
            startButton.setEnabled(false);
        });
    }

    @Override public void onControlAck(String operation, int status, int session, boolean logging) {
        runOnUiThread(() -> {
            if ("STOP".equals(operation) && stopPending) completeLocalStop();
            if (status == 0)
                setStatus(operation + " acknowledged by CYD session S" + String.format("%04d", session) +
                        (logging ? "." : "; logger closed."));
            else
                setStatus(operation + " rejected by CYD, status " + status + ".");
        });
    }
}
