package com.jafinch78.toyotacansync;

import android.annotation.SuppressLint;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothProfile;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanFilter;
import android.bluetooth.le.ScanResult;
import android.bluetooth.le.ScanSettings;
import android.content.Context;
import android.os.Build;
import android.os.ParcelUuid;
import android.os.SystemClock;
import android.util.SparseArray;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Collections;
import java.util.UUID;

final class BleSyncManager {
    static final UUID SERVICE_UUID = UUID.fromString("6ed9f000-4f21-4c8c-a8a7-923c86b40001");
    static final UUID COMMAND_UUID = UUID.fromString("6ed9f000-4f21-4c8c-a8a7-923c86b40002");
    static final UUID RESPONSE_UUID = UUID.fromString("6ed9f000-4f21-4c8c-a8a7-923c86b40003");
    private static final UUID CCCD_UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");

    interface Listener {
        void onStatus(String status);
        void onReady(String name, String address);
        void onDisconnected();
        void onControlAck(String operation, int status, int session, boolean logging);
    }

    private static final class PendingControl {
        final String operation;
        final long sendNs;
        PendingControl(String operation, long sendNs) {
            this.operation = operation;
            this.sendNs = sendNs;
        }
    }

    private final Context context;
    private final Listener listener;
    private final SparseArray<Long> pendingTimes = new SparseArray<>();
    private final SparseArray<PendingControl> pendingControls = new SparseArray<>();
    private BluetoothLeScanner scanner;
    private BluetoothGatt gatt;
    private BluetoothGattCharacteristic commandCharacteristic;
    private int sequence = 1;
    private boolean ready;
    private String deviceName = "";
    private String deviceAddress = "";

    BleSyncManager(Context context, Listener listener) {
        this.context = context.getApplicationContext();
        this.listener = listener;
    }

    boolean isReady() { return ready && gatt != null && commandCharacteristic != null; }
    String deviceName() { return deviceName; }
    String deviceAddress() { return deviceAddress; }

    @SuppressLint("MissingPermission")
    void scanAndConnect() {
        BluetoothManager manager = (BluetoothManager) context.getSystemService(Context.BLUETOOTH_SERVICE);
        BluetoothAdapter adapter = manager == null ? null : manager.getAdapter();
        if (adapter == null || !adapter.isEnabled()) {
            listener.onStatus("Bluetooth is unavailable or turned off.");
            return;
        }
        scanner = adapter.getBluetoothLeScanner();
        if (scanner == null) {
            listener.onStatus("BLE scanner unavailable.");
            return;
        }
        listener.onStatus("Scanning for ToyotaCYD...");
        ScanFilter filter = new ScanFilter.Builder()
                .setServiceUuid(new ParcelUuid(SERVICE_UUID)).build();
        ScanSettings settings = new ScanSettings.Builder()
                .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build();
        scanner.startScan(Collections.singletonList(filter), settings, scanCallback);
    }

    @SuppressLint("MissingPermission")
    void close() {
        ready = false;
        if (scanner != null) scanner.stopScan(scanCallback);
        if (gatt != null) {
            gatt.disconnect();
            gatt.close();
            gatt = null;
        }
    }

    int sendTimeProbe() {
        if (!isReady()) return -1;
        int seq = nextSequence();
        long t1 = SystemClock.elapsedRealtimeNanos();
        pendingTimes.put(seq, t1);
        ByteBuffer packet = ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN);
        packet.put((byte) 0x01).put((byte) 0x01).putShort((short) seq);
        if (!write(packet.array())) {
            pendingTimes.remove(seq);
            return -1;
        }
        return seq;
    }

    int sendControl(String operation, int opcode, int marker) {
        if (!isReady()) return -1;
        int seq = nextSequence();
        long sendNs = SystemClock.elapsedRealtimeNanos();
        pendingControls.put(seq, new PendingControl(operation, sendNs));
        ByteBuffer packet = ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN);
        packet.put((byte) 0x02).put((byte) 0x01).putShort((short) seq);
        packet.put((byte) opcode).put((byte) 0).putShort((short) marker);
        if (!write(packet.array())) {
            pendingControls.remove(seq);
            return -1;
        }
        return seq;
    }

    private int nextSequence() {
        int result = sequence++ & 0xFFFF;
        if (result == 0) result = sequence++ & 0xFFFF;
        return result;
    }

    @SuppressLint("MissingPermission")
    private boolean write(byte[] packet) {
        if (gatt == null || commandCharacteristic == null) return false;
        if (Build.VERSION.SDK_INT >= 33) {
            return gatt.writeCharacteristic(commandCharacteristic, packet,
                    BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE) == BluetoothGatt.GATT_SUCCESS;
        }
        commandCharacteristic.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE);
        commandCharacteristic.setValue(packet);
        return gatt.writeCharacteristic(commandCharacteristic);
    }

    private final ScanCallback scanCallback = new ScanCallback() {
        @Override public void onScanResult(int callbackType, ScanResult result) {
            connect(result.getDevice());
        }

        @Override public void onScanFailed(int errorCode) {
            listener.onStatus("BLE scan failed: " + errorCode);
        }
    };

    @SuppressLint("MissingPermission")
    private void connect(BluetoothDevice device) {
        if (scanner != null) scanner.stopScan(scanCallback);
        deviceName = device.getName() == null ? "ToyotaCYD" : device.getName();
        deviceAddress = device.getAddress();
        listener.onStatus("Connecting to " + deviceName + "...");
        if (Build.VERSION.SDK_INT >= 23)
            gatt = device.connectGatt(context, false, gattCallback, BluetoothDevice.TRANSPORT_LE);
        else
            gatt = device.connectGatt(context, false, gattCallback);
    }

    private final BluetoothGattCallback gattCallback = new BluetoothGattCallback() {
        @SuppressLint("MissingPermission")
        @Override public void onConnectionStateChange(BluetoothGatt source, int status, int newState) {
            if (status == BluetoothGatt.GATT_SUCCESS && newState == BluetoothProfile.STATE_CONNECTED) {
                listener.onStatus("Discovering ToyotaCYD sync service...");
                source.discoverServices();
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                ready = false;
                listener.onDisconnected();
            }
        }

        @SuppressLint("MissingPermission")
        @Override public void onServicesDiscovered(BluetoothGatt source, int status) {
            if (status != BluetoothGatt.GATT_SUCCESS) {
                listener.onStatus("BLE service discovery failed: " + status);
                return;
            }
            BluetoothGattService service = source.getService(SERVICE_UUID);
            BluetoothGattCharacteristic response = service == null ? null : service.getCharacteristic(RESPONSE_UUID);
            commandCharacteristic = service == null ? null : service.getCharacteristic(COMMAND_UUID);
            if (response == null || commandCharacteristic == null) {
                listener.onStatus("Connected device is not a compatible ToyotaCYD logger.");
                return;
            }
            source.setCharacteristicNotification(response, true);
            BluetoothGattDescriptor descriptor = response.getDescriptor(CCCD_UUID);
            if (descriptor == null) {
                markReady();
            } else if (Build.VERSION.SDK_INT >= 33) {
                source.writeDescriptor(descriptor, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
            } else {
                descriptor.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
                source.writeDescriptor(descriptor);
            }
        }

        @Override public void onDescriptorWrite(BluetoothGatt source, BluetoothGattDescriptor descriptor, int status) {
            if (status == BluetoothGatt.GATT_SUCCESS) markReady();
            else listener.onStatus("BLE notification setup failed: " + status);
        }

        @Override public void onCharacteristicChanged(BluetoothGatt source,
                                                       BluetoothGattCharacteristic characteristic) {
            handleResponse(characteristic.getValue());
        }

        @Override public void onCharacteristicChanged(BluetoothGatt source,
                                                       BluetoothGattCharacteristic characteristic,
                                                       byte[] value) {
            handleResponse(value);
        }
    };

    private void markReady() {
        ready = true;
        listener.onReady(deviceName, deviceAddress);
    }

    private void handleResponse(byte[] value) {
        long receiveNs = SystemClock.elapsedRealtimeNanos();
        if (value == null || value.length < 4 || value[1] != 1) return;
        ByteBuffer packet = ByteBuffer.wrap(value).order(ByteOrder.LITTLE_ENDIAN);
        int type = packet.get() & 0xFF;
        packet.get();
        int seq = packet.getShort() & 0xFFFF;
        if (type == 0x81 && value.length >= 20) {
            Long t1 = pendingTimes.get(seq);
            pendingTimes.remove(seq);
            long e2Us = packet.getLong();
            long e3Us = packet.getLong();
            if (t1 != null) SyncStore.addSync(seq, t1, e2Us, e3Us, receiveNs);
            return;
        }
        if (type == 0x82 && value.length >= 20) {
            PendingControl pending = pendingControls.get(seq);
            pendingControls.remove(seq);
            int status = packet.get() & 0xFF;
            boolean logging = (packet.get() & 0xFF) != 0;
            int session = packet.getInt();
            long eventUs = packet.getLong();
            boolean diagnostic = (packet.get() & 0xFF) != 0;
            boolean normal = (packet.get() & 0xFF) != 0;
            String operation = pending == null ? "UNKNOWN" : pending.operation;
            long sendNs = pending == null ? 0 : pending.sendNs;
            SyncStore.addControl(operation, seq, sendNs, receiveNs, status, session,
                    eventUs, logging, diagnostic, normal);
            listener.onControlAck(operation, status, session, logging);
        }
    }
}
