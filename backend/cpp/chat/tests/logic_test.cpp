#include <gtest/gtest.h>

#include "logic.hpp"

TEST(LogicTest, ReplyIsConstant) {
  EXPECT_EQ(chat::logic::GenerateReply("hello"), chat::logic::kReply);
  EXPECT_EQ(chat::logic::GenerateReply("another request"), chat::logic::kReply);
}
