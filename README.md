

# CarConnectivity Connector for Volvo Vehicles
[![GitHub sourcecode](https://img.shields.io/badge/Source-GitHub-green)](https://github.com/tillsteinbach/CarConnectivity-connector-volvo/)
[![GitHub release (latest by date)](https://img.shields.io/github/v/release/tillsteinbach/CarConnectivity-connector-volvo)](https://github.com/tillsteinbach/CarConnectivity-connector-volvo/releases/latest)
[![GitHub](https://img.shields.io/github/license/tillsteinbach/CarConnectivity-connector-volvo)](https://github.com/tillsteinbach/CarConnectivity-connector-volvo/blob/master/LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/tillsteinbach/CarConnectivity-connector-volvo)](https://github.com/tillsteinbach/CarConnectivity-connector-volvo/issues)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/carconnectivity-connector-volvo?label=PyPI%20Downloads)](https://pypi.org/project/carconnectivity-connector-volvo/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/carconnectivity-connector-volvo)](https://pypi.org/project/carconnectivity-connector-volvo/)
[![Donate at PayPal](https://img.shields.io/badge/Donate-PayPal-2997d8)](https://www.paypal.com/donate?hosted_button_id=2BVFF5GJ9SXAJ)
[![Sponsor at Github](https://img.shields.io/badge/Sponsor-GitHub-28a745)](https://github.com/sponsors/tillsteinbach)

[CarConnectivity](https://github.com/tillsteinbach/CarConnectivity) is a python API to connect to various car services. This connector enables the integration of Volvo vehicles through the WeConnect API. Look at [CarConnectivity](https://github.com/tillsteinbach/CarConnectivity) for other supported brands.

## Configuration
In your carconnectivity.json configuration add a section for the volvo connector like this:
```
{
    "carConnectivity": {
        "connectors": [
            {
                "type": "volvo",
                "config": {
                    "vcc_api_key_primary": "d64b33a7067a4c428def9474964", // API Key primary
                    "vcc_api_key_secondary": "de0c63a885ffdac4ccc92d8744905611caf", // API Key secondary
                    "connected_vehicle_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6InhqTzF5SDVmM29WendVeWRVNDJwSzZ0c2d4OF9SUzI1NiIsInBpLmF0bSI6Ijl0MWYifQ.eyJzY29wZSI6ImNvbnZlOmJyYWtlX3N0YXR1cyBjb252ZTpmdWVsX3N0YXR1cyBjb252ZTpkb29yc19zdGF0dXMgb3BlbmlkIGNvbnZlOmRpYWdub3N0aWNzX3dvcmtzaG9wIGNvbnZlOnRyaXBfc3RhdGlzdGljcyBjb252ZTplbnZpcm9ubWVudCBjb252ZTpvZG9tZXRlclasd9sadiu29udmU6ZW5naW5lX3N0YXR1cyBjb252ZTpsb2NrX3N0YXR1cyBjb252ZTp2ZWhpY2xlX3JlbGF0aW9uIGNvbnZlOndpbmRvd3Nfc3RhdHVzIGNvbnZlOnR5cmVfc3RhdHVzIGNvbnZlOmNvbm5lY3Rpdml0eV9zdGF0dXMgY29udmU6ZGlhZ25vc3RpY3NfZW5naW5lX3N0YXR1cyBjb252ZTp3YXJuaW5ncyIsImNsaWVudF9pZCI6Im1vamlwaXhfMTAiLCJncm50aWQiOiJ1dUNBUXNVeEhuR0ZmdHNIWHVEM253SVFpUjBmc3M0TSIsImlzcyI6Imh0dHBzOi8vdm9sdm9pZC5ldS52b2x2b2NhcnMuY29tIiwiaWF0IjoxNzQyNjU1NjYxLCJqdGkiOiJTdEJFNlhVMHRPQVg2ZTI3YWV5RktYI55as7d7sdYi1iZjUwLTRlMGEtYmU5Ny1kYjkzNmMxMGEzYjQiLCJwaS5zcmkiOiJHRl8tN0ZscXhEOEFnSnoxdlRncG1wTi1TTkUuLnZmQ2IuZkRjSkllM0U0c0N4dWxWWWxSWDhrMFhVMSIsInVzZXJOYW1lIjoiZGV2ZWxvcGVydm9sdm9jYXJzY29tQGdtYWlsLmNvbSIsImVtYWlsIjoiZGV2ZWxvcGVydm9sdm9jYXJzY29tQGdtYWlsLmNvbSIsImV4cCI6MTc0MjY1NzQ2MX0.FpiSQ21r_IayMW4OOuGtwaRjeqqfxptnYOHqxQO7lwOJjwlBnefDEeit2BkJg75rOLDrd8sd8sdsdnqC-uL1FnalrctNRfN0tsxtWn-8RmzmhcqbC6ukgRo-LtWUjbkYmeF1KS_JDnJOrTWOKcdiH9594rardL1DtozVNp9EvsVfOf6HK-MAy8FD5ocf1wpoVsUxvvKHyv1FHzNlMP2Qy-iq_qhaTzxs6m5UxhgZVWReqxWvOmAeyPSV5GMD8i_0724x2uAHDPI342yVpyorTKPGX-qKOPTRoMu8o92li5Ea0cigmK7RYiqgb0fm9k4gvf9WTiVX4EgbMiw", //Access token for the vehicle
                }
            }
        ]
    }
}
```
