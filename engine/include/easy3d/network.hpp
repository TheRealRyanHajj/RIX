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
