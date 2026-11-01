#include "easy3d/network.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <random>
#include <stdexcept>
#include <utility>

namespace easy3d {

TransportEventQueue::TransportEventQueue(const std::size_t capacity)
    : capacity_(capacity) {
    if (capacity == 0) {
        throw std::invalid_argument("transport event queue capacity must be positive");
    }
}

bool TransportEventQueue::try_push(TransportEvent event) {
    const std::scoped_lock lock(mutex_);
    if (events_.size() >= capacity_) {
        ++overflow_count_;
        return false;
    }
    events_.push_back(std::move(event));
    return true;
}

std::vector<TransportEvent> TransportEventQueue::drain(
    const std::size_t maximum_count) {
    if (maximum_count == 0) {
        throw std::invalid_argument("maximum transport events must be positive");
    }
    const std::scoped_lock lock(mutex_);
    const std::size_t count = std::min(maximum_count, events_.size());
    std::vector<TransportEvent> result;
    result.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        result.push_back(std::move(events_.front()));
        events_.pop_front();
    }
    return result;
}

std::size_t TransportEventQueue::size() const {
    const std::scoped_lock lock(mutex_);
    return events_.size();
}

std::size_t TransportEventQueue::capacity() const noexcept { return capacity_; }

std::uint64_t TransportEventQueue::overflow_count() const {
    const std::scoped_lock lock(mutex_);
    return overflow_count_;
}

namespace {

constexpr std::size_t endpoint_count = 2;
constexpr std::size_t maximum_disconnect_reason_size = 256;

struct ScheduledMessage final {
    double delivery_time{0.0};
    std::uint64_t sequence{0};
    std::size_t sender{0};
    NetworkDelivery delivery{NetworkDelivery::Reliable};
    std::vector<std::uint8_t> payload;
};

void validate_config(const SimulatedNetworkConfig& config) {
    if (!std::isfinite(config.one_way_latency_seconds) ||
        config.one_way_latency_seconds < 0.0) {
        throw std::invalid_argument("simulated latency must be finite and non-negative");
    }
    if (!std::isfinite(config.jitter_seconds) || config.jitter_seconds < 0.0) {
        throw std::invalid_argument("simulated jitter must be finite and non-negative");
    }
    if (!std::isfinite(config.loss_probability) || config.loss_probability < 0.0 ||
        config.loss_probability > 1.0) {
        throw std::invalid_argument("simulated loss must be between zero and one");
    }
    if (config.in_flight_capacity == 0 || config.event_queue_capacity == 0 ||
        config.maximum_message_size == 0) {
        throw std::invalid_argument("network queue and message limits must be positive");
    }
}

} // namespace

struct SimulatedNetwork::Impl final {
    explicit Impl(const SimulatedNetworkConfig& input)
        : config(input),
          queues{std::make_unique<TransportEventQueue>(input.event_queue_capacity),
                 std::make_unique<TransportEventQueue>(input.event_queue_capacity)},
          random(input.random_seed) {
        validate_config(input);
    }

    SimulatedNetworkConfig config;
    std::array<std::unique_ptr<TransportEventQueue>, endpoint_count> queues;
    std::array<TransportStats, endpoint_count> stats;
    std::array<bool, endpoint_count> overflow_pending{false, false};
    bool connected{true};
    double current_time{0.0};
    std::uint64_t next_sequence{1};
    std::vector<ScheduledMessage> scheduled;
    std::mt19937_64 random;
    mutable std::mutex mutex;
};

SimulatedNetwork::Endpoint::Endpoint(SimulatedNetwork& network,
                                     const std::size_t side,
                                     const ConnectionId connection)
    : network_(&network), side_(side), connection_(connection) {}

ConnectionId SimulatedNetwork::Endpoint::connection() const noexcept {
    return connection_;
}

SendStatus SimulatedNetwork::Endpoint::send(
    const ConnectionId connection,
    const std::span<const std::uint8_t> payload,
    const NetworkDelivery delivery) {
    return network_->send(side_, connection, payload, delivery);
}

void SimulatedNetwork::Endpoint::disconnect(const ConnectionId connection,
                                            std::string reason) {
    network_->disconnect(side_, connection, std::move(reason));
}

std::vector<TransportEvent> SimulatedNetwork::Endpoint::poll(
    const std::size_t maximum_events) {
    return network_->poll(side_, maximum_events);
}

TransportStats SimulatedNetwork::Endpoint::stats() const {
    return network_->stats(side_);
}

SimulatedNetwork::SimulatedNetwork(SimulatedNetworkConfig config)
    : impl_(std::make_unique<Impl>(config)),
      first_(*this, 0, ConnectionId{1}),
      second_(*this, 1, ConnectionId{2}) {
    const bool first_connected = impl_->queues[0]->try_push(
        {TransportEventType::Connected, first_.connection()});
    const bool second_connected = impl_->queues[1]->try_push(
        {TransportEventType::Connected, second_.connection()});
    if (!first_connected || !second_connected) {
        throw NetworkError("simulated network could not queue connection events");
    }
}

SimulatedNetwork::~SimulatedNetwork() = default;

SimulatedNetwork::Endpoint& SimulatedNetwork::first() noexcept { return first_; }

SimulatedNetwork::Endpoint& SimulatedNetwork::second() noexcept { return second_; }

SendStatus SimulatedNetwork::send(const std::size_t side,
                                  const ConnectionId connection,
                                  const std::span<const std::uint8_t> payload,
                                  const NetworkDelivery delivery) {
    const std::scoped_lock lock(impl_->mutex);
    TransportStats& statistics = impl_->stats.at(side);
    const ConnectionId expected = side == 0 ? first_.connection() : second_.connection();
    if (!impl_->connected || connection != expected) {
        ++statistics.queue_rejections;
        return SendStatus::InvalidConnection;
    }
    if (payload.size() > impl_->config.maximum_message_size) {
        ++statistics.queue_rejections;
        return SendStatus::MessageTooLarge;
    }
    if (impl_->scheduled.size() >= impl_->config.in_flight_capacity) {
        ++statistics.queue_rejections;
        return SendStatus::QueueFull;
    }

    double jitter = 0.0;
    if (impl_->config.jitter_seconds > 0.0) {
        std::uniform_real_distribution<double> distribution(
            -impl_->config.jitter_seconds, impl_->config.jitter_seconds);
        jitter = distribution(impl_->random);
    }
    const double delay = std::max(0.0, impl_->config.one_way_latency_seconds + jitter);
    const std::uint64_t sequence = impl_->next_sequence++;
    impl_->scheduled.push_back({impl_->current_time + delay,
                                sequence,
                                side,
                                delivery,
                                {payload.begin(), payload.end()}});
    ++statistics.messages_sent;
    statistics.bytes_sent += payload.size();
    return SendStatus::Queued;
}

void SimulatedNetwork::disconnect(const std::size_t side,
                                  const ConnectionId connection,
                                  std::string reason) {
    if (reason.size() > maximum_disconnect_reason_size) {
        throw std::invalid_argument("disconnect reason exceeds 256 bytes");
    }
    const std::scoped_lock lock(impl_->mutex);
    const ConnectionId expected = side == 0 ? first_.connection() : second_.connection();
    if (!impl_->connected || connection != expected) {
        throw NetworkError("cannot disconnect an invalid connection");
    }
    impl_->connected = false;
    for (const ScheduledMessage& message : impl_->scheduled) {
        ++impl_->stats[message.sender].messages_lost;
    }
    impl_->scheduled.clear();
    for (std::size_t endpoint = 0; endpoint < endpoint_count; ++endpoint) {
        const ConnectionId identifier =
            endpoint == 0 ? first_.connection() : second_.connection();
        if (!impl_->queues[endpoint]->try_push({TransportEventType::Disconnected,
                                                identifier,
                                                NetworkDelivery::Reliable,
                                                {},
                                                reason,
                                                0})) {
            ++impl_->stats[endpoint].event_overflows;
            impl_->overflow_pending[endpoint] = true;
        }
    }
}

void SimulatedNetwork::advance(const double elapsed_seconds) {
    if (!std::isfinite(elapsed_seconds) || elapsed_seconds < 0.0) {
        throw std::invalid_argument("simulated elapsed time must be finite and non-negative");
    }
    const std::scoped_lock lock(impl_->mutex);
    impl_->current_time += elapsed_seconds;
    std::stable_sort(impl_->scheduled.begin(),
                     impl_->scheduled.end(),
                     [](const ScheduledMessage& left, const ScheduledMessage& right) {
                         if (left.delivery_time != right.delivery_time) {
                             return left.delivery_time < right.delivery_time;
                         }
                         return left.sequence < right.sequence;
                     });

    std::size_t delivered = 0;
    std::uniform_real_distribution<double> loss_distribution(0.0, 1.0);
    while (delivered < impl_->scheduled.size() &&
           impl_->scheduled[delivered].delivery_time <= impl_->current_time) {
        ScheduledMessage& message = impl_->scheduled[delivered];
        const bool lost = impl_->config.loss_probability > 0.0 &&
                          loss_distribution(impl_->random) <
                              impl_->config.loss_probability;
        if (lost) {
            ++impl_->stats[message.sender].messages_lost;
        } else if (impl_->connected) {
            const std::size_t receiver = 1 - message.sender;
            TransportEvent event{TransportEventType::Message,
                                 receiver == 0 ? first_.connection()
                                               : second_.connection(),
                                 message.delivery,
                                 std::move(message.payload),
                                 {},
                                 message.sequence};
            const std::size_t bytes = event.payload.size();
            if (impl_->queues[receiver]->try_push(std::move(event))) {
                ++impl_->stats[receiver].messages_received;
                impl_->stats[receiver].bytes_received += bytes;
            } else {
                ++impl_->stats[receiver].event_overflows;
                impl_->overflow_pending[receiver] = true;
            }
        }
        ++delivered;
    }
    impl_->scheduled.erase(impl_->scheduled.begin(),
                           impl_->scheduled.begin() +
                               static_cast<std::ptrdiff_t>(delivered));
}

std::vector<TransportEvent> SimulatedNetwork::poll(
    const std::size_t side, const std::size_t maximum_events) {
    {
        const std::scoped_lock lock(impl_->mutex);
        if (impl_->overflow_pending.at(side)) {
            impl_->overflow_pending[side] = false;
            throw NetworkError("transport event queue capacity exhausted");
        }
    }
    return impl_->queues.at(side)->drain(maximum_events);
}

TransportStats SimulatedNetwork::stats(const std::size_t side) const {
    const std::scoped_lock lock(impl_->mutex);
    return impl_->stats.at(side);
}

double SimulatedNetwork::time_seconds() const {
    const std::scoped_lock lock(impl_->mutex);
    return impl_->current_time;
}

std::size_t SimulatedNetwork::in_flight_count() const {
    const std::scoped_lock lock(impl_->mutex);
    return impl_->scheduled.size();
}

} // namespace easy3d
