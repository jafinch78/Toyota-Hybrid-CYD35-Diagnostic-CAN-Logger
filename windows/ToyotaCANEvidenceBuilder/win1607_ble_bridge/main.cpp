// Win1607_BLE_Bridge
// Transport-only ToyotaCYD-Sync/1 bridge for Windows 10 1607 / build 14393.
// Build as C++/CX (/ZW) against the Windows 10 SDK 10.0.14393.0.

#include <windows.h>
#include <collection.h>
#include <concrt.h>
#include <iostream>
#include <iomanip>
#include <mutex>
#include <sstream>
#include <string>
#include <vector>

using namespace concurrency;
using namespace Platform;
using namespace Windows::Devices::Bluetooth;
using namespace Windows::Devices::Bluetooth::GenericAttributeProfile;
using namespace Windows::Devices::Enumeration;
using namespace Windows::Storage::Streams;

namespace {

const Guid SERVICE_UUID(0x6ed9f000, 0x4f21, 0x4c8c, 0xa8, 0xa7, 0x92, 0x3c, 0x86, 0xb4, 0x00, 0x01);
const Guid COMMAND_UUID(0x6ed9f000, 0x4f21, 0x4c8c, 0xa8, 0xa7, 0x92, 0x3c, 0x86, 0xb4, 0x00, 0x02);
const Guid RESPONSE_UUID(0x6ed9f000, 0x4f21, 0x4c8c, 0xa8, 0xa7, 0x92, 0x3c, 0x86, 0xb4, 0x00, 0x03);

std::mutex output_mutex;

void emit_line(const std::string& line) {
    std::lock_guard<std::mutex> lock(output_mutex);
    std::cout << line << "\n";
    std::cout.flush();
}

std::string narrow(String^ value) {
    if (value == nullptr) return std::string();
    std::wstring wide(value->Data());
    if (wide.empty()) return std::string();
    int size = WideCharToMultiByte(CP_UTF8, 0, wide.c_str(), static_cast<int>(wide.size()),
                                   nullptr, 0, nullptr, nullptr);
    if (size <= 0) return std::string();
    std::string result(static_cast<std::size_t>(size), '\0');
    WideCharToMultiByte(CP_UTF8, 0, wide.c_str(), static_cast<int>(wide.size()),
                        &result[0], size, nullptr, nullptr);
    return result;
}

bool decode_hex(const std::string& text, std::vector<unsigned char>& out) {
    if (text.empty() || (text.size() & 1U)) return false;
    out.clear();
    out.reserve(text.size() / 2);
    for (std::size_t i = 0; i < text.size(); i += 2) {
        unsigned int value = 0;
        std::istringstream parser(text.substr(i, 2));
        parser >> std::hex >> value;
        if (!parser || value > 0xFF) return false;
        out.push_back(static_cast<unsigned char>(value));
    }
    return true;
}

std::string encode_hex(const std::vector<unsigned char>& data) {
    std::ostringstream stream;
    stream << std::hex << std::setfill('0');
    for (unsigned char value : data) stream << std::setw(2) << static_cast<unsigned int>(value);
    return stream.str();
}

IBuffer^ make_buffer(const std::vector<unsigned char>& bytes) {
    DataWriter^ writer = ref new DataWriter();
    auto array = ref new Array<unsigned char>(bytes.data(), static_cast<unsigned int>(bytes.size()));
    writer->WriteBytes(array);
    return writer->DetachBuffer();
}

std::vector<unsigned char> read_buffer(IBuffer^ buffer) {
    std::vector<unsigned char> bytes;
    if (buffer == nullptr || buffer->Length == 0) return bytes;
    DataReader^ reader = DataReader::FromBuffer(buffer);
    auto array = ref new Array<unsigned char>(buffer->Length);
    reader->ReadBytes(array);
    bytes.reserve(array->Length);
    for (unsigned int i = 0; i < array->Length; ++i) bytes.push_back(array[i]);
    return bytes;
}

GattCharacteristic^ find_characteristic(GattDeviceService^ service, Guid uuid) {
    if (service == nullptr) return nullptr;
    auto characteristics = service->GetAllCharacteristics();
    for (unsigned int i = 0; i < characteristics->Size; ++i) {
        auto characteristic = characteristics->GetAt(i);
        if (characteristic != nullptr && characteristic->Uuid == uuid) return characteristic;
    }
    return nullptr;
}

class LegacyBleTransport {
public:
    LegacyBleTransport() : connected_(false), notification_token_{} {}
    ~LegacyBleTransport() { disconnect(); }

    bool connect_auto(std::string& error) {
        disconnect();
        try {
            String^ selector = BluetoothLEDevice::GetDeviceSelectorFromPairingState(true);
            auto devices = create_task(DeviceInformation::FindAllAsync(selector)).get();
            if (devices == nullptr || devices->Size == 0) {
                error = "no paired Bluetooth LE devices found; pair the ToyotaCYD logger in Windows Settings first";
                return false;
            }

            for (unsigned int i = 0; i < devices->Size; ++i) {
                DeviceInformation^ info = devices->GetAt(i);
                if (info == nullptr || !info->Pairing->IsPaired) continue;

                BluetoothLEDevice^ candidate = nullptr;
                try {
                    candidate = create_task(BluetoothLEDevice::FromIdAsync(info->Id)).get();
                    if (candidate == nullptr) continue;

                    GattDeviceService^ service = candidate->GetGattService(SERVICE_UUID);
                    if (service == nullptr) {
                        delete candidate;
                        continue;
                    }

                    GattCharacteristic^ command = find_characteristic(service, COMMAND_UUID);
                    GattCharacteristic^ response = find_characteristic(service, RESPONSE_UUID);
                    if (command == nullptr || response == nullptr) {
                        delete service;
                        delete candidate;
                        continue;
                    }

                    device_ = candidate;
                    service_ = service;
                    command_ = command;
                    response_ = response;

                    notification_token_ = response_->ValueChanged +=
                        ref new Windows::Foundation::TypedEventHandler<GattCharacteristic^, GattValueChangedEventArgs^>(
                            this, &LegacyBleTransport::on_value_changed);

                    GattCommunicationStatus notify_status = create_task(
                        response_->WriteClientCharacteristicConfigurationDescriptorAsync(
                            GattClientCharacteristicConfigurationDescriptorValue::Notify)).get();
                    if (notify_status != GattCommunicationStatus::Success) {
                        response_->ValueChanged -= notification_token_;
                        clear_handles();
                        continue;
                    }

                    connected_ = true;
                    device_name_ = narrow(candidate->Name);
                    device_id_ = narrow(info->Id);
                    return true;
                }
                catch (Exception^ ex) {
                    if (candidate != nullptr && candidate != device_) delete candidate;
                    error = "candidate failed: " + narrow(ex->Message);
                    clear_handles();
                }
            }

            if (error.empty()) error = "paired ToyotaCYD service/characteristics not found";
            return false;
        }
        catch (Exception^ ex) {
            error = narrow(ex->Message);
            disconnect();
            return false;
        }
    }

    bool write(const std::vector<unsigned char>& payload, std::string& error) {
        if (!connected_ || command_ == nullptr) {
            error = "not connected";
            return false;
        }
        if (payload.size() != 4 && payload.size() != 8) {
            error = "ToyotaCYD-Sync/1 command must be 4 or 8 bytes";
            return false;
        }

        try {
            IBuffer^ buffer = make_buffer(payload);
            GattCommunicationStatus status = create_task(
                command_->WriteValueAsync(buffer, GattWriteOption::WriteWithoutResponse)).get();
            if (status != GattCommunicationStatus::Success) {
                error = "GATT write returned non-success status";
                return false;
            }
            return true;
        }
        catch (Exception^ ex) {
            error = narrow(ex->Message);
            return false;
        }
    }

    void disconnect() {
        connected_ = false;
        if (response_ != nullptr) {
            try {
                response_->ValueChanged -= notification_token_;
                create_task(response_->WriteClientCharacteristicConfigurationDescriptorAsync(
                    GattClientCharacteristicConfigurationDescriptorValue::None)).wait();
            }
            catch (...) {
            }
        }
        clear_handles();
        device_name_.clear();
        device_id_.clear();
    }

    const std::string& device_name() const { return device_name_; }
    const std::string& device_id() const { return device_id_; }

private:
    void on_value_changed(GattCharacteristic^, GattValueChangedEventArgs^ args) {
        try {
            std::vector<unsigned char> bytes = read_buffer(args->CharacteristicValue);
            if (!bytes.empty()) emit_line("RX " + encode_hex(bytes));
        }
        catch (Exception^ ex) {
            emit_line("ERR RX " + narrow(ex->Message));
        }
    }

    void clear_handles() {
        command_ = nullptr;
        response_ = nullptr;
        if (service_ != nullptr) {
            delete service_;
            service_ = nullptr;
        }
        if (device_ != nullptr) {
            delete device_;
            device_ = nullptr;
        }
    }

    bool connected_;
    BluetoothLEDevice^ device_ = nullptr;
    GattDeviceService^ service_ = nullptr;
    GattCharacteristic^ command_ = nullptr;
    GattCharacteristic^ response_ = nullptr;
    Windows::Foundation::EventRegistrationToken notification_token_;
    std::string device_name_;
    std::string device_id_;
};

} // namespace

int main() {
    LegacyBleTransport ble;
    std::string line;

    emit_line("READY Win1607_BLE_Bridge protocol=1");

    while (std::getline(std::cin, line)) {
        if (line == "QUIT") break;

        if (line == "CONNECT AUTO" || line == "CONNECT") {
            std::string error;
            if (ble.connect_auto(error)) {
                emit_line("OK CONNECTED " + ble.device_name() + "\t" + ble.device_id());
            } else {
                emit_line("ERR CONNECT " + error);
            }
            continue;
        }

        if (line.rfind("WRITE ", 0) == 0) {
            std::vector<unsigned char> payload;
            if (!decode_hex(line.substr(6), payload)) {
                emit_line("ERR WRITE invalid hex");
                continue;
            }
            std::string error;
            if (ble.write(payload, error)) emit_line("OK WRITE");
            else emit_line("ERR WRITE " + error);
            continue;
        }

        if (line == "DISCONNECT") {
            ble.disconnect();
            emit_line("OK DISCONNECTED");
            continue;
        }

        emit_line("ERR COMMAND unsupported command");
    }

    ble.disconnect();
    return 0;
}
