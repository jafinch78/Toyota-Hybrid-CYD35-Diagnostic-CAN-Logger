// Win1607_BLE_Bridge
// Transport-only ToyotaCYD-Sync/1 bridge for Windows 10 1607 / build 14393.
//
// This initial source intentionally contains only the IPC shell and packet
// validation boundary. The WinRT 14393 GATT implementation is added behind
// LegacyBleTransport so packet/timing semantics never migrate into C++.

#include <algorithm>
#include <cctype>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {

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

class LegacyBleTransport {
public:
    bool connect_auto(std::string& error) {
        // TODO(14393): enumerate paired BLE devices using Windows.Devices.Enumeration,
        // resolve ToyotaCYD, BluetoothLEDevice::FromIdAsync(), legacy GetGattService(),
        // legacy characteristic enumeration, and enable RESPONSE CCCD notifications.
        error = "WinRT 14393 GATT backend not implemented yet";
        return false;
    }

    bool write(const std::vector<unsigned char>& payload, std::string& error) {
        if (!connected_) {
            error = "not connected";
            return false;
        }
        // ToyotaCYD-Sync/1 currently uses only 4-byte sync and 8-byte control
        // requests. Reject other sizes here so IPC mistakes cannot become BLE writes.
        if (payload.size() != 4 && payload.size() != 8) {
            error = "ToyotaCYD-Sync/1 command must be 4 or 8 bytes";
            return false;
        }
        // TODO(14393): convert bytes to IBuffer and write command characteristic.
        error = "WinRT 14393 GATT write backend not implemented yet";
        return false;
    }

    void disconnect() { connected_ = false; }

private:
    bool connected_ = false;
};

} // namespace

int main() {
    LegacyBleTransport ble;
    std::string line;

    while (std::getline(std::cin, line)) {
        if (line == "QUIT") break;

        if (line.rfind("CONNECT ", 0) == 0) {
            std::string error;
            if (ble.connect_auto(error)) std::cout << "OK CONNECTED\n";
            else std::cout << "ERR CONNECT " << error << "\n";
            std::cout.flush();
            continue;
        }

        if (line.rfind("WRITE ", 0) == 0) {
            std::vector<unsigned char> payload;
            if (!decode_hex(line.substr(6), payload)) {
                std::cout << "ERR WRITE invalid hex\n";
                std::cout.flush();
                continue;
            }
            std::string error;
            if (ble.write(payload, error)) std::cout << "OK WRITE\n";
            else std::cout << "ERR WRITE " << error << "\n";
            std::cout.flush();
            continue;
        }

        if (line == "DISCONNECT") {
            ble.disconnect();
            std::cout << "OK DISCONNECTED\n";
            std::cout.flush();
            continue;
        }

        std::cout << "ERR COMMAND unsupported command\n";
        std::cout.flush();
    }
    return 0;
}
