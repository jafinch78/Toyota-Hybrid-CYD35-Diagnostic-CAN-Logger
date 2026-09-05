package com.jafinch78.toyotacansync;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.MediaRecorder;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.IBinder;
import android.os.SystemClock;
import android.util.DisplayMetrics;
import android.view.WindowManager;

import androidx.core.app.NotificationCompat;

import java.io.File;

public class CaptureService extends Service {
    static final String ACTION_START = "com.jafinch78.toyotacansync.START";
    static final String ACTION_STOP = "com.jafinch78.toyotacansync.STOP";
    static final String EXTRA_RESULT_CODE = "resultCode";
    static final String EXTRA_RESULT_DATA = "resultData";
    private static final int NOTIFICATION_ID = 2401;
    private static final String CHANNEL_ID = "toyota_can_capture";
    static volatile boolean running;

    private MediaProjection projection;
    private MediaRecorder recorder;
    private VirtualDisplay virtualDisplay;
    private boolean stopping;

    @Override public void onCreate() {
        super.onCreate();
        createChannel();
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) return START_NOT_STICKY;
        if (ACTION_STOP.equals(intent.getAction())) {
            stopCapture(true);
            stopSelf();
            return START_NOT_STICKY;
        }
        if (!ACTION_START.equals(intent.getAction()) || running) return START_NOT_STICKY;
        startAsForeground();
        int resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, 0);
        Intent resultData;
        if (Build.VERSION.SDK_INT >= 33)
            resultData = intent.getParcelableExtra(EXTRA_RESULT_DATA, Intent.class);
        else
            resultData = intent.getParcelableExtra(EXTRA_RESULT_DATA);
        try {
            startCapture(resultCode, resultData);
        } catch (Exception error) {
            SyncStore.recordingStopped(SystemClock.elapsedRealtimeNanos(), false);
            stopSelf();
        }
        return START_NOT_STICKY;
    }

    private void startAsForeground() {
        // Notification.Builder(Context, channelId) is API 26+.
        // NotificationCompat keeps the foreground notification valid on API 23
        // while still using CHANNEL_ID on Android 8.0 and newer.
        Notification notification = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setSmallIcon(android.R.drawable.presence_video_online)
                .setContentTitle("Toyota CAN synchronized capture")
                .setContentText("Screen and microphone recording are active")
                .setOngoing(true)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .build();
        if (Build.VERSION.SDK_INT >= 30) {
            startForeground(NOTIFICATION_ID, notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION |
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE |
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE);
        } else if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIFICATION_ID, notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION |
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE);
        } else {
            startForeground(NOTIFICATION_ID, notification);
        }
    }

    @SuppressWarnings("deprecation")
    private void startCapture(int resultCode, Intent resultData) throws Exception {
        if (resultData == null || !SyncStore.isOpen())
            throw new IllegalStateException("Missing MediaProjection approval or session");
        MediaProjectionManager manager = (MediaProjectionManager)
                getSystemService(Context.MEDIA_PROJECTION_SERVICE);
        projection = manager.getMediaProjection(resultCode, resultData);
        projection.registerCallback(new MediaProjection.Callback() {
            @Override public void onStop() { stopCapture(false); }
        }, null);

        DisplayMetrics metrics = new DisplayMetrics();
        WindowManager windowManager = (WindowManager) getSystemService(Context.WINDOW_SERVICE);
        windowManager.getDefaultDisplay().getRealMetrics(metrics);
        int width = Math.max(640, metrics.widthPixels - (metrics.widthPixels % 16));
        int height = Math.max(640, metrics.heightPixels - (metrics.heightPixels % 16));
        File output = SyncStore.videoFile();

        recorder = new MediaRecorder();
        recorder.setAudioSource(MediaRecorder.AudioSource.MIC);
        recorder.setVideoSource(MediaRecorder.VideoSource.SURFACE);
        recorder.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);
        recorder.setOutputFile(output.getAbsolutePath());
        recorder.setVideoEncoder(MediaRecorder.VideoEncoder.H264);
        recorder.setVideoEncodingBitRate(8_000_000);
        recorder.setVideoFrameRate(30);
        recorder.setVideoSize(width, height);
        recorder.setAudioEncoder(MediaRecorder.AudioEncoder.AAC);
        recorder.setAudioEncodingBitRate(128_000);
        recorder.setAudioSamplingRate(44_100);
        recorder.prepare();

        virtualDisplay = projection.createVirtualDisplay("ToyotaCANSync",
                width, height, metrics.densityDpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                recorder.getSurface(), null, null);
        long beforeNs = SystemClock.elapsedRealtimeNanos();
        recorder.start();
        long afterNs = SystemClock.elapsedRealtimeNanos();
        running = true;
        SyncStore.recordingStarted(beforeNs, afterNs, width, height, metrics.densityDpi);
    }

    private synchronized void stopCapture(boolean clean) {
        if (stopping) return;
        stopping = true;
        long stopNs = SystemClock.elapsedRealtimeNanos();
        try { if (recorder != null) recorder.stop(); } catch (Exception ignored) { clean = false; }
        try { if (recorder != null) recorder.reset(); } catch (Exception ignored) {}
        try { if (recorder != null) recorder.release(); } catch (Exception ignored) {}
        recorder = null;
        if (virtualDisplay != null) virtualDisplay.release();
        virtualDisplay = null;
        if (projection != null) projection.stop();
        projection = null;
        running = false;
        SyncStore.recordingStopped(stopNs, clean);
        if (Build.VERSION.SDK_INT >= 24) stopForeground(STOP_FOREGROUND_REMOVE);
        else stopForeground(true);
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationChannel channel = new NotificationChannel(CHANNEL_ID,
                "Synchronized capture", NotificationManager.IMPORTANCE_LOW);
        channel.setDescription("Toyota CAN synchronized screen and narration recording");
        NotificationManager manager = (NotificationManager)
                getSystemService(Context.NOTIFICATION_SERVICE);
        manager.createNotificationChannel(channel);
    }

    @Override public void onDestroy() {
        if (running) stopCapture(false);
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent intent) { return null; }
}
