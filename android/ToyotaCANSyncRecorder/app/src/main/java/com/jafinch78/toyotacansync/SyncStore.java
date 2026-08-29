package com.jafinch78.toyotacansync;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;

import androidx.core.content.FileProvider;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

final class SyncStore {
    private static File sessionDirectory;
    private static File videoFile;
    private static JSONObject root;
    private static JSONArray samples;
    private static JSONArray controls;
    private static JSONArray markers;

    private SyncStore() {}

    static synchronized File begin(Context context) {
        File base = context.getExternalFilesDir(Environment.DIRECTORY_MOVIES);
        if (base == null) base = context.getFilesDir();
        SimpleDateFormat directoryFormat = new SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US);
        sessionDirectory = new File(base, "ToyotaCANSync/CAPTURE_" + directoryFormat.format(new Date()));
        if (!sessionDirectory.mkdirs() && !sessionDirectory.isDirectory())
            throw new IllegalStateException("Cannot create capture directory");
        videoFile = new File(sessionDirectory, "SCREEN.mp4");
        samples = new JSONArray();
        controls = new JSONArray();
        markers = new JSONArray();
        root = new JSONObject();
        try {
            root.put("format", "ToyotaCANSync-AndroidCapture");
            root.put("format_version", "1.0");
            root.put("app_version", "1.0.0");
            root.put("ble_protocol", "ToyotaCYD-Sync/1");
            root.put("android_model", Build.MANUFACTURER + " " + Build.MODEL);
            root.put("android_version", Build.VERSION.RELEASE);
            root.put("sdk_int", Build.VERSION.SDK_INT);
            root.put("clock", "android.os.SystemClock.elapsedRealtimeNanos");
            root.put("created_utc", utcNow());
            root.put("video_file", videoFile.getName());
            root.put("sync_samples", samples);
            root.put("control_events", controls);
            root.put("markers", markers);
            root.put("closed_cleanly", false);
        } catch (Exception ignored) {}
        writeJson();
        return videoFile;
    }

    static synchronized boolean isOpen() { return root != null && sessionDirectory != null; }
    static synchronized File videoFile() { return videoFile; }
    static synchronized File sessionDirectory() { return sessionDirectory; }

    static synchronized void setBleDevice(String name, String address) {
        if (root == null) return;
        try {
            root.put("ble_device_name", name);
            root.put("ble_device_address", address);
        } catch (Exception ignored) {}
        writeJson();
    }

    static synchronized void recordingStarted(long beforeNs, long afterNs, int width, int height, int densityDpi) {
        if (root == null) return;
        try {
            root.put("video_start_call_before_ns", beforeNs);
            root.put("video_start_call_after_ns", afterNs);
            root.put("video_anchor_ns", beforeNs + (afterNs - beforeNs) / 2L);
            root.put("video_anchor_uncertainty_ns", Math.max(16_666_667L, afterNs - beforeNs));
            root.put("video_width", width);
            root.put("video_height", height);
            root.put("display_density_dpi", densityDpi);
            root.put("recording_started_utc", utcNow());
        } catch (Exception ignored) {}
        writeJson();
    }

    static synchronized void addSync(int sequence, long t1Ns, long e2Us, long e3Us, long t4Ns) {
        if (samples == null) return;
        try {
            JSONObject item = new JSONObject();
            item.put("sequence", sequence);
            item.put("t1_android_ns", t1Ns);
            item.put("t1_client_ns", t1Ns);
            item.put("e2_esp_us", e2Us);
            item.put("e3_esp_us", e3Us);
            item.put("t4_android_ns", t4Ns);
            item.put("t4_client_ns", t4Ns);
            item.put("round_trip_ns", t4Ns - t1Ns - (e3Us - e2Us) * 1000L);
            item.put("android_midpoint_ns", t1Ns + (t4Ns - t1Ns) / 2L);
            item.put("esp_midpoint_us", e2Us + (e3Us - e2Us) / 2L);
            samples.put(item);
        } catch (Exception ignored) {}
        writeJson();
    }

    static synchronized void addControl(String operation, int sequence, long sendNs,
                                        long ackNs, int status, int session, long espEventUs,
                                        boolean logging, boolean diagnostics, boolean twaiNormal) {
        if (controls == null) return;
        try {
            JSONObject item = new JSONObject();
            item.put("operation", operation);
            item.put("sequence", sequence);
            item.put("android_send_ns", sendNs);
            item.put("android_ack_ns", ackNs);
            item.put("status", status);
            item.put("cyd_session", session);
            item.put("esp_event_us", espEventUs);
            item.put("logging_after", logging);
            item.put("diagnostics_after", diagnostics);
            item.put("twai_normal_after", twaiNormal);
            controls.put(item);
        } catch (Exception ignored) {}
        writeJson();
    }

    static synchronized void addLocalMarker(int marker, long androidNs) {
        if (markers == null) return;
        try {
            JSONObject item = new JSONObject();
            item.put("marker", marker);
            item.put("android_ns", androidNs);
            markers.put(item);
        } catch (Exception ignored) {}
        writeJson();
    }

    static synchronized void recordingStopped(long stopNs, boolean clean) {
        if (root == null) return;
        try {
            root.put("video_stop_ns", stopNs);
            root.put("recording_stopped_utc", utcNow());
            root.put("closed_cleanly", clean);
        } catch (Exception ignored) {}
        writeJson();
    }

    static synchronized File buildShareZip(Context context) throws Exception {
        if (sessionDirectory == null || !sessionDirectory.isDirectory())
            throw new IllegalStateException("No capture is available");
        File exportDir = new File(context.getCacheDir(), "exports");
        if (!exportDir.mkdirs() && !exportDir.isDirectory())
            throw new IllegalStateException("Cannot create export directory");
        File zip = new File(exportDir, sessionDirectory.getName() + ".zip");
        byte[] buffer = new byte[64 * 1024];
        try (ZipOutputStream output = new ZipOutputStream(new FileOutputStream(zip))) {
            File[] files = sessionDirectory.listFiles();
            if (files != null) for (File file : files) {
                if (!file.isFile()) continue;
                output.putNextEntry(new ZipEntry(file.getName()));
                try (FileInputStream input = new FileInputStream(file)) {
                    int count;
                    while ((count = input.read(buffer)) > 0) output.write(buffer, 0, count);
                }
                output.closeEntry();
            }
        }
        return zip;
    }

    static void shareLast(Activity activity) throws Exception {
        File zip = buildShareZip(activity);
        Uri uri = FileProvider.getUriForFile(activity,
                activity.getPackageName() + ".files", zip);
        Intent share = new Intent(Intent.ACTION_SEND);
        share.setType("application/zip");
        share.putExtra(Intent.EXTRA_STREAM, uri);
        share.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        activity.startActivity(Intent.createChooser(share, "Share synchronized capture"));
    }

    private static void writeJson() {
        if (root == null || sessionDirectory == null) return;
        File target = new File(sessionDirectory, "CAPTURE_SYNC.json");
        File temporary = new File(sessionDirectory, "CAPTURE_SYNC.tmp");
        try (OutputStreamWriter writer = new OutputStreamWriter(
                new FileOutputStream(temporary), StandardCharsets.UTF_8)) {
            writer.write(root.toString(2));
            writer.flush();
            if (target.exists() && !target.delete()) return;
            if (!temporary.renameTo(target)) {
                try (FileOutputStream out = new FileOutputStream(target)) {
                    out.write(root.toString(2).getBytes(StandardCharsets.UTF_8));
                }
                temporary.delete();
            }
        } catch (Exception ignored) {}
    }

    private static String utcNow() {
        SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US);
        format.setTimeZone(TimeZone.getTimeZone("UTC"));
        return format.format(new Date());
    }
}
