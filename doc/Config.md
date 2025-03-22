

# CarConnectivity Connector for Volvo Config Options
The configuration for CarConnectivity is a .json file.
## Volvo Connector Options
These are the valid options for the Volvo Connector
```json
{
    "carConnectivity": {
        "connectors": [
            {
                "type": "volvo", // Definition for the Volvo Connector
                "config": {
                    "log_level": "error", // set the connectos log level
                    "interval": 300, // Interval in which the server is checked in seconds
                    "vcc_api_key_primary": "d64b33a7067a4c428def9474964", // API Key primary
                    "vcc_api_key_secondary": "de0c63a885ffdac4ccc92d8744905611caf", // API Key secondary
                    "connected_vehicle_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6InhqTzF5SDVmM29WendVeWRVNDJwSzZ0c2d4OF9SUzI1NiIsInBpLmF0bSI6Ijl0MWYifQ.eyJzY29wZSI6ImNvbnZlOmJyYWtlX3N0YXR1cyBjb252ZTpmdWVsX3N0YXR1cyBjb252ZTpkb29yc19zdGF0dXMgb3BlbmlkIGNvbnZlOmRpYWdub3N0aWNzX3dvcmtzaG9wIGNvbnZlOnRyaXBfc3RhdGlzdGljcyBjb252ZTplbnZpcm9ubWVudCBjb252ZTpvZG9tZXRlclasd9sadiu29udmU6ZW5naW5lX3N0YXR1cyBjb252ZTpsb2NrX3N0YXR1cyBjb252ZTp2ZWhpY2xlX3JlbGF0aW9uIGNvbnZlOndpbmRvd3Nfc3RhdHVzIGNvbnZlOnR5cmVfc3RhdHVzIGNvbnZlOmNvbm5lY3Rpdml0eV9zdGF0dXMgY29udmU6ZGlhZ25vc3RpY3NfZW5naW5lX3N0YXR1cyBjb252ZTp3YXJuaW5ncyIsImNsaWVudF9pZCI6Im1vamlwaXhfMTAiLCJncm50aWQiOiJ1dUNBUXNVeEhuR0ZmdHNIWHVEM253SVFpUjBmc3M0TSIsImlzcyI6Imh0dHBzOi8vdm9sdm9pZC5ldS52b2x2b2NhcnMuY29tIiwiaWF0IjoxNzQyNjU1NjYxLCJqdGkiOiJTdEJFNlhVMHRPQVg2ZTI3YWV5RktYI55as7d7sdYi1iZjUwLTRlMGEtYmU5Ny1kYjkzNmMxMGEzYjQiLCJwaS5zcmkiOiJHRl8tN0ZscXhEOEFnSnoxdlRncG1wTi1TTkUuLnZmQ2IuZkRjSkllM0U0c0N4dWxWWWxSWDhrMFhVMSIsInVzZXJOYW1lIjoiZGV2ZWxvcGVydm9sdm9jYXJzY29tQGdtYWlsLmNvbSIsImVtYWlsIjoiZGV2ZWxvcGVydm9sdm9jYXJzY29tQGdtYWlsLmNvbSIsImV4cCI6MTc0MjY1NzQ2MX0.FpiSQ21r_IayMW4OOuGtwaRjeqqfxptnYOHqxQO7lwOJjwlBnefDEeit2BkJg75rOLDrd8sd8sdsdnqC-uL1FnalrctNRfN0tsxtWn-8RmzmhcqbC6ukgRo-LtWUjbkYmeF1KS_JDnJOrTWOKcdiH9594rardL1DtozVNp9EvsVfOf6HK-MAy8FD5ocf1wpoVsUxvvKHyv1FHzNlMP2Qy-iq_qhaTzxs6m5UxhgZVWReqxWvOmAeyPSV5GMD8i_0724x2uAHDPI342yVpyorTKPGX-qKOPTRoMu8o92li5Ea0cigmK7RYiqgb0fm9k4gvf9WTiVX4EgbMiw", //Access token for the vehicle
                    "api_log_level": "debug", // Show debug information regarding the API
                    "max_age": 300 //Cache requests to the server vor MAX_AGE seconds
                }
            }
        ],
        "plugins": []
    }
}
```