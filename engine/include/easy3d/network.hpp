#pragma once

#include "easy3d/core.hpp"

#include <cstddef>
#include <cstdint>
#include <deque>
#include <memory>
#include <mutex>
#include <span>
#include <string>
#include <vector>

namespace easy3d {

class NetworkError : public EngineError {
public:
    using EngineError::EngineError;
};

struct ConnectionId final {
    std::uint64_t value{0};

    [[nodiscard]] constexpr bool valid() const noexcept { return value != 0; }
    explicit constexpr operator bool() const noexcept { return valid(); }
    friend auto operator<=>(const ConnectionId&, const ConnectionId&) = default;
};

enum class NetworkDelivery : std::uint8_t {
    Reliable,
    Unreliable,
};

enum class TransportEventType : std::uint8_t {
    Connected,
    Disconnected,
    Message,
};

enum class SendStatus : std::uint8_t {
    Queued,
    InvalidConnection,
    MessageTooLarge,
    QueueFull,
};

struct TransportEvent final {
    TransportEventType type{TransportEventType::Message};
    ConnectionId connection;
    NetworkDelivery delivery{NetworkDelivery::Reliable};
    std::vector<std::uint8_t> payload;
    std::string reason;
    std::uint64_t sequence{0};
    std::uint16_t disconnect_code{0};
};

struct TransportStats final {
    std::uint64_t messages_sent{0};
    std::uint64_t messages_received{0};
    std::uint64_t messages_lost{0};
    std::uint64_t bytes_sent{0};
    std::uint64_t bytes_received{0};
    std::uint64_t queue_rejections{0};
    std::uint64_t event_overflows{0};

    friend bool operator==(const TransportStats&, const TransportStats&) = default;
};

struct NetworkBackendInfo final {
    bool available{false};
    std::string name;
    std::string version;
    std::string crypto_provider;
};

enum class NetworkClientState : std::uint8_t {
    Disconnected,
    Connecting,
    Handshaking,
    Connected,
};

struct NetworkClientConfig final {
    double connection_timeout_seconds{5.0};
    double peer_timeout_seconds{10.0};
    std::size_t event_queue_capacity{1024};
    std::size_t maximum_message_size{64 * 1024};
    std::uint16_t protocol_version{1};
    std::uint32_t schema_version{1};
};

struct NetworkConnectionMetrics final {
    NetworkClientState state{NetworkClientState::Disconnected};
    int ping_milliseconds{-1};
    double outgoing_bytes_per_second{0.0};
    double incoming_bytes_per_second{0.0};
    std::uint64_t pending_reliable_bytes{0};
    std::uint64_t pending_unreliable_bytes{0};
    std::uint32_t negotiated_maximum_message_size{0};
    TransportStats transport;
};

enum class NetworkServerState : std::uint8_t {
    Stopped,
    Listening,
};

struct NetworkServerConfig final {
    std::string bind_address{"0.0.0.0"};
    std::uint16_t port{7777};
    std::size_t maximum_connections{32};
    double handshake_timeout_seconds{5.0};
    double peer_timeout_seconds{10.0};
    std::size_t event_queue_capacity{4096};
    std::size_t maximum_message_size{64 * 1024};
    std::uint16_t protocol_version{1};
    std::uint32_t schema_version{1};
};

[[nodiscard]] NetworkBackendInfo network_backend_info();

class NetworkBackendRuntime final {
public:
    NetworkBackendRuntime();
    ~NetworkBackendRuntime();

    NetworkBackendRuntime(const NetworkBackendRuntime&) = delete;
    NetworkBackendRuntime& operator=(const NetworkBackendRuntime&) = delete;
    NetworkBackendRuntime(NetworkBackendRuntime&&) = delete;
    NetworkBackendRuntime& operator=(NetworkBackendRuntime&&) = delete;

    [[nodiscard]] bool ready() const noexcept;
    [[nodiscard]] bool loopback_smoke_test() const;

private:
    bool acquired_{false};
};

class TransportEventQueue final {
public:
    explicit TransportEventQueue(std::size_t capacity);

    TransportEventQueue(const TransportEventQueue&) = delete;
    TransportEventQueue& operator=(const TransportEventQueue&) = delete;

    [[nodiscard]] bool try_push(TransportEvent event);
    [[nodiscard]] std::vector<TransportEvent> drain(std::size_t maximum_count);
    [[nodiscard]] std::size_t size() const;
    [[nodiscard]] std::size_t capacity() const noexcept;
    [[nodiscard]] std::uint64_t overflow_count() const;

private:
    const std::size_t capacity_;
    mutable std::mutex mutex_;
    std::deque<TransportEvent> events_;
    std::uint64_t overflow_count_{0};
};

class NetworkTransport {
public:
    virtual ~NetworkTransport() = default;

    [[nodiscard]] virtual SendStatus send(ConnectionId connection,
                                          std::span<const std::uint8_t> payload,
                                          NetworkDelivery delivery) = 0;
    virtual void disconnect(ConnectionId connection, std::string reason) = 0;
    [[nodiscard]] virtual std::vector<TransportEvent> poll(
        std::size_t maximum_events) = 0;
    [[nodiscard]] virtual TransportStats stats() const = 0;
};

class NetworkClient final : public NetworkTransport {
public:
    explicit NetworkClient(NetworkClientConfig config = {});
    ~NetworkClient() override;

    NetworkClient(const NetworkClient&) = delete;
    NetworkClient& operator=(const NetworkClient&) = delete;
    NetworkClient(NetworkClient&&) = delete;
    NetworkClient& operator=(NetworkClient&&) = delete;

    // Numeric IPv4 or IPv6 only. DNS and discovery remain separate policies.
    void connect(std::string address, std::uint16_t port);
    [[nodiscard]] ConnectionId connection() const noexcept;
    [[nodiscard]] NetworkClientState state() const noexcept;
    [[nodiscard]] std::string remote_address() const;
    [[nodiscard]] NetworkConnectionMetrics metrics() const;

    [[nodiscard]] SendStatus send(ConnectionId connection,
                                  std::span<const std::uint8_t> payload,
                                  NetworkDelivery delivery) override;
    void disconnect(ConnectionId connection, std::string reason) override;
    [[nodiscard]] std::vector<TransportEvent> poll(
        std::size_t maximum_events) override;
    [[nodiscard]] TransportStats stats() const override;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

class NetworkServer final : public NetworkTransport {
public:
    explicit NetworkServer(NetworkServerConfig config = {});
    ~NetworkServer() override;

    NetworkServer(const NetworkServer&) = delete;
    NetworkServer& operator=(const NetworkServer&) = delete;
    NetworkServer(NetworkServer&&) = delete;
    NetworkServer& operator=(NetworkServer&&) = delete;

    void start();
    void stop(std::string reason = "server stopped");
    [[nodiscard]] NetworkServerState state() const noexcept;
    [[nodiscard]] std::uint16_t port() const noexcept;
    [[nodiscard]] std::string bind_address() const;
    [[nodiscard]] std::vector<ConnectionId> connections() const;

    [[nodiscard]] SendStatus send(ConnectionId connection,
                                  std::span<const std::uint8_t> payload,
                                  NetworkDelivery delivery) override;
    void disconnect(ConnectionId connection, std::string reason) override;
    [[nodiscard]] std::vector<TransportEvent> poll(
        std::size_t maximum_events) override;
    [[nodiscard]] TransportStats stats() const override;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

struct SimulatedNetworkConfig final {
    double one_way_latency_seconds{0.0};
    double jitter_seconds{0.0};
    double loss_probability{0.0};
    std::uint64_t random_seed{1};
    std::size_t in_flight_capacity{1024};
    std::size_t event_queue_capacity{1024};
    std::size_t maximum_message_size{64 * 1024};
};

class SimulatedNetwork final {
public:
    class Endpoint final : public NetworkTransport {
    public:
        [[nodiscard]] ConnectionId connection() const noexcept;
        [[nodiscard]] SendStatus send(ConnectionId connection,
                                      std::span<const std::uint8_t> payload,
                                      NetworkDelivery delivery) override;
        void disconnect(ConnectionId connection, std::string reason) override;
        [[nodiscard]] std::vector<TransportEvent> poll(
            std::size_t maximum_events) override;
        [[nodiscard]] TransportStats stats() const override;

    private:
        friend class SimulatedNetwork;
        Endpoint(SimulatedNetwork& network, std::size_t side, ConnectionId connection);

        SimulatedNetwork* network_;
        std::size_t side_;
        ConnectionId connection_;
    };

    explicit SimulatedNetwork(SimulatedNetworkConfig config = {});
    ~SimulatedNetwork();

    SimulatedNetwork(const SimulatedNetwork&) = delete;
    SimulatedNetwork& operator=(const SimulatedNetwork&) = delete;
    SimulatedNetwork(SimulatedNetwork&&) = delete;
    SimulatedNetwork& operator=(SimulatedNetwork&&) = delete;

    [[nodiscard]] Endpoint& first() noexcept;
    [[nodiscard]] Endpoint& second() noexcept;
    void advance(double elapsed_seconds);
    [[nodiscard]] double time_seconds() const;
    [[nodiscard]] std::size_t in_flight_count() const;

private:
    struct Impl;

    [[nodiscard]] SendStatus send(std::size_t side,
                                  ConnectionId connection,
                                  std::span<const std::uint8_t> payload,
                                  NetworkDelivery delivery);
    void disconnect(std::size_t side, ConnectionId connection, std::string reason);
    [[nodiscard]] std::vector<TransportEvent> poll(std::size_t side,
                                                   std::size_t maximum_events);
    [[nodiscard]] TransportStats stats(std::size_t side) const;

    std::unique_ptr<Impl> impl_;
    Endpoint first_;
    Endpoint second_;
};

} // namespace easy3d
