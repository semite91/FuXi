# FuXi

A personal flashcard app that helps one learner build English vocabulary through timed push notifications and personalised word content.

## Language

### Learner and words

**Learner**:
The single person who uses FuXi. There is exactly one Learner.
_Avoid_: User account, customer

**Word**:
An English vocabulary item with its translation that the Learner wants to learn.
_Avoid_: Card, term, vocabulary entry

**Word Content**:
The personalised material (story, picture, quote, music or movie reference) shown on the back of a Flashcard to help the Learner remember a Word.
_Avoid_: Description, RAG result

**Flashcard**:
A two-sided card for one Word: the front asks whether the Learner knows the Word, the back shows its translation, Word Content and Word History.
_Avoid_: Card item

**Word History**:
The record of every Yes/No answer the Learner has given for a Word.
_Avoid_: Log, answers

**Known**:
The state of a Word the Learner has confirmed they know.
_Avoid_: Learned, mastered

### Rotation

**Rotation**:
The limited set of Words currently being presented to the Learner, drawn from not-yet-Known Words and Reinforced Words. A Word stays in the Rotation after it becomes Known.
_Avoid_: Active list, queue

**Reinforced Word**:
A Word the Learner has permanently flagged for extra review. Flagging it takes it out of the Rotation; when it is drawn back in, it is due after the Reinforcement Period.
_Avoid_: Starred, flagged, difficult word

**Due**:
The state of a Word in the Rotation whose waiting time has passed, so it can be presented again.
_Avoid_: Ready, pending

**Rotation Count**:
The maximum number of Words in the Rotation at once.

**Rotation Period**:
The base waiting time, in minutes, before a Word in the Rotation is due again.

**Reinforcement Period**:
The waiting time, in minutes, before a Word flagged for reinforcement is due again.

### Notifications

**Notification Period**:
How often, in minutes, FuXi checks whether to send a push notification.

**Notification Window**:
A specific date-time range, picked on the schedule calendar, during which push notifications may be sent.
_Avoid_: Schedule, available time, period

**Push Subscription**:
A browser's registration to receive FuXi's push notifications on one device.
_Avoid_: Device token
