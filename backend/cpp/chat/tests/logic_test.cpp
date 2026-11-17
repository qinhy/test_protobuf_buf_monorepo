#include <gtest/gtest.h>

#include <chrono>
#include <string>
#include <variant>
#include <vector>

#include "logic.hpp"

TEST(LogicTest, ReplyIsConstant) {
  EXPECT_EQ(chat::logic::GenerateReply("hello"), chat::logic::kReply);
  EXPECT_EQ(chat::logic::GenerateReply("another request"), chat::logic::kReply);
  EXPECT_EQ(chat::logic::CompleteReply("hello"), chat::logic::kReply);
}

TEST(LogicTest, StreamReplyEmitsOrderedEvents) {
  std::vector<chat::events::ChatDomainEvent> events;
  chat::logic::StreamReply(
      "hello",
      [&](const chat::events::ChatDomainEvent& event) {
        events.push_back(event);
        return true;
      },
      4, std::chrono::milliseconds(0));

  ASSERT_GE(events.size(), 3u);
  for (size_t i = 0; i < events.size(); ++i) {
    EXPECT_EQ(chat::events::EventSequence(events[i]),
              static_cast<uint32_t>(i + 1));
  }
  EXPECT_TRUE(std::holds_alternative<chat::events::Started>(events.front()));

  std::string deltas;
  for (const auto& event : events) {
    if (const auto* delta = std::get_if<chat::events::Delta>(&event)) {
      deltas += delta->text;
    }
  }
  EXPECT_EQ(deltas, chat::logic::kReply);

  const auto* done = std::get_if<chat::events::Completed>(&events.back());
  ASSERT_NE(done, nullptr);
  EXPECT_EQ(done->reply, chat::logic::kReply);
}
