#include "easy3d/network.hpp"

#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

int fail(const int code, const char* const message) {
    std::cerr << message << '\n';
    return code;
}

std::vector<std::uint8_t> bytes(const std::string& value) {
    return {value.begin(), value.end()};
}

} // namespace

int main() {
    try {
        easy3d::TransportEventQueue queue(2);
        if (!queue.try_push({easy3d::TransportEventType::Connected,
                             easy3d::ConnectionId{11}}) ||
            !queue.try_push({easy3d::TransportEventType::Message,
                             easy3d::ConnectionId{11},
                             easy3d::NetworkDelivery::Reliable,
                             bytes("one")}) ||
            queue.try_push({easy3d::TransportEventType::Message,
                            easy3d::ConnectionId{11},
                            easy3d::NetworkDelivery::Reliable,
                            bytes("overflow")})) {
            return fail(1, "bounded transport event queue did not reject overflow");
        }
        if (queue.size() != 2 || queue.capacity() != 2 || queue.overflow_count() != 1) {
            return fail(2, "bounded transport event queue counters are incorrect");
        }
        const auto one_event = queue.drain(1);
        if (one_event.size() != 1 ||
            one_event[0].type != easy3d::TransportEventType::Connected ||
            queue.size() != 1) {
            return fail(3, "bounded transport event queue lost FIFO ordering");
        }

        easy3d::SimulatedNetworkConfig config;
        config.one_way_latency_seconds = 0.050;
        config.random_seed = 7;
        config.in_flight_capacity = 2;
        config.event_queue_capacity = 4;
        config.maximum_message_size = 8;
        easy3d::SimulatedNetwork network(config);
        easy3d::NetworkTransport& first = network.first();
        easy3d::NetworkTransport& second = network.second();
        const auto first_connected = first.poll(4);
        const auto second_connected = second.poll(4);
        if (first_connected.size() != 1 || second_connected.size() != 1 ||
            first_connected[0].type != easy3d::TransportEventType::Connected ||
            second_connected[0].type != easy3d::TransportEventType::Connected) {
            return fail(4, "simulated endpoints did not emit connected events");
        }

        const std::vector<std::uint8_t> hello = bytes("hello");
        const std::vector<std::uint8_t> world = bytes("world");
        if (first.send(network.first().connection(),
                       hello,
                       easy3d::NetworkDelivery::Reliable) !=
                easy3d::SendStatus::Queued ||
            first.send(network.first().connection(),
                       world,
                       easy3d::NetworkDelivery::Unreliable) !=
                easy3d::SendStatus::Queued ||
            first.send(network.first().connection(),
                       hello,
                       easy3d::NetworkDelivery::Reliable) !=
                easy3d::SendStatus::QueueFull) {
            return fail(5, "simulated in-flight queue did not enforce capacity");
        }
        network.advance(0.049);
        if (!second.poll(4).empty()) {
            return fail(6, "simulated message arrived before configured latency");
        }
        network.advance(0.001);
        const auto delivered = second.poll(4);
        if (delivered.size() != 2 || delivered[0].payload != hello ||
            delivered[1].payload != world || delivered[0].sequence >= delivered[1].sequence ||
            delivered[0].delivery != easy3d::NetworkDelivery::Reliable ||
            delivered[1].delivery != easy3d::NetworkDelivery::Unreliable) {
            return fail(7, "simulated delivery metadata or ordering is incorrect");
        }
        const easy3d::TransportStats first_stats = first.stats();
        const easy3d::TransportStats second_stats = second.stats();
        if (first_stats.messages_sent != 2 || first_stats.bytes_sent != 10 ||
            first_stats.queue_rejections != 1 || second_stats.messages_received != 2 ||
            second_stats.bytes_received != 10) {
            return fail(8, "simulated transport statistics are incorrect");
        }
        if (first.send(easy3d::ConnectionId{99},
                       hello,
                       easy3d::NetworkDelivery::Reliable) !=
                easy3d::SendStatus::InvalidConnection ||
            first.send(network.first().connection(),
                       bytes("too-large"),
                       easy3d::NetworkDelivery::Reliable) !=
                easy3d::SendStatus::MessageTooLarge) {
            return fail(9, "simulated send validation is incorrect");
        }

        easy3d::SimulatedNetworkConfig loss_config;
        loss_config.loss_probability = 1.0;
        loss_config.random_seed = 42;
        easy3d::SimulatedNetwork loss_network(loss_config);
        static_cast<void>(loss_network.first().poll(1));
        static_cast<void>(loss_network.second().poll(1));
        static_cast<void>(loss_network.first().send(
            loss_network.first().connection(),
            hello,
            easy3d::NetworkDelivery::Unreliable));
        loss_network.advance(0.0);
        if (!loss_network.second().poll(1).empty() ||
            loss_network.first().stats().messages_lost != 1) {
            return fail(10, "simulated packet loss is incorrect");
        }

        easy3d::SimulatedNetworkConfig overflow_config;
        overflow_config.event_queue_capacity = 1;
        overflow_config.in_flight_capacity = 2;
        easy3d::SimulatedNetwork overflow_network(overflow_config);
        static_cast<void>(overflow_network.first().poll(1));
        static_cast<void>(overflow_network.second().poll(1));
        static_cast<void>(overflow_network.first().send(
            overflow_network.first().connection(),
            hello,
            easy3d::NetworkDelivery::Reliable));
        static_cast<void>(overflow_network.first().send(
            overflow_network.first().connection(),
            world,
            easy3d::NetworkDelivery::Reliable));
        overflow_network.advance(0.0);
        try {
            static_cast<void>(overflow_network.second().poll(1));
            return fail(11, "event queue exhaustion was not surfaced");
        } catch (const easy3d::NetworkError&) {
            // Expected; the next poll can drain the event that fit.
        }
        if (overflow_network.second().poll(1).size() != 1 ||
            overflow_network.second().stats().event_overflows != 1) {
            return fail(12, "event queue overflow recovery is incorrect");
        }

        network.first().disconnect(network.first().connection(), "test complete");
        const auto first_disconnected = first.poll(1);
        const auto second_disconnected = second.poll(1);
        if (first_disconnected.size() != 1 || second_disconnected.size() != 1 ||
            first_disconnected[0].reason != "test complete" ||
            first.send(network.first().connection(),
                       hello,
                       easy3d::NetworkDelivery::Reliable) !=
                easy3d::SendStatus::InvalidConnection) {
            return fail(13, "simulated disconnect lifecycle is incorrect");
        }

        std::cout << "easy3d_network_tests: PASS\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "easy3d_network_tests: FAIL: " << error.what() << '\n';
        return 14;
    }
}
