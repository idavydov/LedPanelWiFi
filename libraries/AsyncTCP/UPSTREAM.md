Vendored from [ESP32Async/AsyncTCP v3.5.0](https://github.com/ESP32Async/AsyncTCP/tree/v3.5.0).
Includes upstream sources, manifests and license. Replaces 1.1.4 to remove
the fixed-capacity TCP event queue and its producer/consumer deadlock paths.
Local patch: `CONFIG_ASYNC_TCP_COOPERATIVE_MS` optionally yields during event
bursts; the S2 profile uses 10 ms to let idle/USB tasks run on its single core.
