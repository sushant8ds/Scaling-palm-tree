# Requirements Document

## Introduction

The Conversation Analysis System automates the review of AI assistant conversations for e-commerce brands. It ingests conversation and message data from MongoDB, analyzes patterns across brands, and surfaces actionable insights to help improve assistant quality — replacing the current manual weekly review process.

The system must identify where the assistant struggles, detect hallucinations and irrelevant product suggestions, surface user frustration signals, and compare performance across brands.

## Glossary

- **System**: The Conversation Analysis System as a whole
- **Conversation**: A single session between a customer and an AI assistant, stored in the `conversations` collection
- **Message**: An individual turn in a conversation, stored in the `messages` collection
- **Brand**: An e-commerce client identified by a unique `widgetId`
- **Assistant**: The AI agent responding to customer queries (sender = "agent")
- **User**: The customer interacting with the assistant (sender = "user")
- **Event**: A non-text interaction message (messageType = "event"), such as a product click
- **Insight**: A structured, actionable finding produced by the System about assistant performance
- **Hallucination**: An assistant response that contains factually incorrect or fabricated information not grounded in the brand's product catalog or policies
- **Drop-off**: A conversation where the user stops responding without a resolution, indicating potential frustration or failure
- **Engagement_Event**: A message with messageType = "event", representing a user interaction such as a product view or quick action click
- **Analysis_Run**: A single execution of the System over a defined dataset or time window

## Requirements

### Requirement 1: Data Ingestion

**User Story:** As an analyst, I want the system to load conversation and message data from MongoDB, so that I can analyze real assistant interactions without manual data extraction.

#### Acceptance Criteria

1. THE System SHALL connect to the `helio_intern` MongoDB database and read from the `conversations` and `messages` collections.
2. WHEN an Analysis_Run is initiated, THE System SHALL join messages to their parent conversations using the `conversationId` field.
3. WHEN an Analysis_Run is initiated, THE System SHALL support filtering by `widgetId` to scope analysis to a specific Brand.
4. WHEN an Analysis_Run is initiated, THE System SHALL support filtering by a date range using the `createdAt` field on conversations.
5. IF the MongoDB connection fails, THEN THE System SHALL emit a descriptive error message and halt the Analysis_Run.
6. IF a conversation contains zero messages, THEN THE System SHALL exclude that conversation from analysis and log a warning.

---

### Requirement 2: Conversation Segmentation

**User Story:** As an analyst, I want conversations grouped by brand and topic type, so that I can compare performance across brands and question categories.

#### Acceptance Criteria

1. THE System SHALL segment conversations by `widgetId` to produce per-Brand analysis.
2. WHEN processing messages, THE System SHALL separate messageType = "text" messages from messageType = "event" messages before performing content analysis.
3. THE System SHALL classify each conversation into at least one topic category (e.g., product question, order issue, recommendation request, policy inquiry) based on the text content of User messages.
4. WHEN a conversation contains messages from both sender = "user" and sender = "agent", THE System SHALL treat it as a complete exchange eligible for quality analysis.
5. IF a conversation contains only sender = "user" messages with no sender = "agent" response, THEN THE System SHALL flag it as an unanswered conversation.

---

### Requirement 3: Drop-off and Frustration Detection

**User Story:** As an analyst, I want to know where users disengage or show frustration, so that I can identify failure points in the assistant experience.

#### Acceptance Criteria

1. WHEN the last message in a conversation has sender = "user" and no subsequent sender = "agent" message exists, THE System SHALL classify that conversation as a Drop-off.
2. THE System SHALL detect frustration signals in User messages, including repeated questions on the same topic within a single conversation, explicit negative sentiment expressions, and messages containing phrases indicating confusion or dissatisfaction.
3. WHEN frustration signals are detected in a conversation, THE System SHALL attach a frustration score between 0 and 1 to that conversation, where 1 represents the highest detected frustration.
4. THE System SHALL compute a drop-off rate per Brand as the ratio of Drop-off conversations to total conversations for that Brand.
5. THE System SHALL compute a frustration rate per Brand as the ratio of conversations with a frustration score above 0.5 to total conversations for that Brand.

---

### Requirement 4: Assistant Response Quality Analysis

**User Story:** As an analyst, I want to understand where the assistant gives poor, irrelevant, or fabricated responses, so that I can prioritize improvements.

#### Acceptance Criteria

1. THE System SHALL evaluate each Assistant response for relevance to the preceding User message within the same conversation.
2. WHEN an Assistant response does not address the topic of the User's message, THE System SHALL flag that response as irrelevant.
3. THE System SHALL detect potential hallucinations by identifying Assistant responses that assert specific product details, prices, availability, or policies that cannot be verified against patterns in the broader dataset for that Brand.
4. WHEN a potential hallucination is detected, THE System SHALL record the conversation ID, the specific message, and a confidence score between 0 and 1 indicating hallucination likelihood.
5. THE System SHALL compute a response quality score per Brand, aggregating relevance and hallucination signals across all conversations for that Brand.
6. WHEN an Assistant response is longer than 500 words, THE System SHALL flag it for review as a potentially over-verbose response.

---

### Requirement 5: Product Suggestion Analysis

**User Story:** As an analyst, I want to know whether the assistant is recommending appropriate products, so that I can detect systematic recommendation failures.

#### Acceptance Criteria

1. THE System SHALL identify conversations where the Assistant made product suggestions, based on the presence of Engagement_Events with metadata.eventType = "product_view" or related product interaction event types.
2. THE System SHALL compute a product engagement rate per Brand as the ratio of conversations containing at least one product Engagement_Event to total conversations for that Brand.
3. WHEN a conversation contains product suggestions but zero Engagement_Events, THE System SHALL flag that conversation as a low-engagement product recommendation.
4. THE System SHALL identify recurring product suggestion patterns per Brand by grouping low-engagement product recommendation conversations by topic category.
5. WHEN a Brand's product engagement rate falls below 10%, THE System SHALL include that Brand in a low-engagement alert within the Insight output.

---

### Requirement 6: Cross-Brand Performance Comparison

**User Story:** As an analyst, I want to compare assistant performance across brands, so that I can identify which brands need the most attention and whether issues are brand-specific or systemic.

#### Acceptance Criteria

1. THE System SHALL compute the following metrics per Brand: total conversations, drop-off rate, frustration rate, response quality score, and product engagement rate.
2. THE System SHALL rank Brands by each metric to identify top-performing and lowest-performing Brands.
3. WHEN a metric for a Brand deviates more than one standard deviation from the mean of that metric across all Brands, THE System SHALL flag that Brand as an outlier for that metric.
4. THE System SHALL identify insights that appear in more than 50% of Brands and classify them as systemic issues.
5. THE System SHALL identify insights that appear in fewer than 20% of Brands and classify them as brand-specific issues.

---

### Requirement 7: Insight Generation and Output

**User Story:** As an analyst, I want the system to produce a structured, readable report of findings, so that I can act on insights without manually interpreting raw data.

#### Acceptance Criteria

1. WHEN an Analysis_Run completes, THE System SHALL produce an Insight report containing: a summary section, per-Brand metric tables, flagged conversations with reasons, and a list of systemic vs. brand-specific issues.
2. THE System SHALL output the Insight report in at least one human-readable format (e.g., Markdown, HTML, or PDF).
3. THE System SHALL output the Insight report in a machine-readable format (JSON) containing all computed metrics and flagged items.
4. WHEN generating the JSON output, THE System SHALL include for each flagged conversation: the conversation ID, widgetId, flag reason, and relevant metric values.
5. THE System SHALL include in the summary section the total number of conversations analyzed, the number of Brands analyzed, the overall drop-off rate, and the top 3 issues by frequency.
6. IF no conversations match the specified filters for an Analysis_Run, THEN THE System SHALL produce an Insight report indicating zero results and the filters applied.

---

### Requirement 8: Trend Analysis Over Time

**User Story:** As an analyst, I want to see how assistant performance changes over time, so that I can measure the impact of improvements.

#### Acceptance Criteria

1. WHEN multiple Analysis_Runs are performed over different date ranges, THE System SHALL store computed metrics per Brand per time window to enable trend comparison.
2. THE System SHALL compute week-over-week change for each per-Brand metric when data for at least two consecutive weeks is available.
3. WHEN a per-Brand metric worsens by more than 10% week-over-week, THE System SHALL flag that change as a regression in the Insight report.
4. WHEN a per-Brand metric improves by more than 10% week-over-week, THE System SHALL highlight that change as an improvement in the Insight report.
