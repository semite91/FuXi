This file is initializer instructor of my project. 

# CONSTRUCTOR
- This is ai first and ai native project.
- An ai first development environment will help to develop this project.
- Ai-first development will be carried out using Claude Code agent harness.
- Project name will be FuXi.
- Domain terms are defined at /GLOSSARY.md. Use them as written.

# CONTENT
  This project is customized flashcard app. It is designed to enhance english vocabulary. 
  It is a single user app. There is one Learner and no authentication.
  PostgreSQL will be used for relational database.
  Secrets will be stored in a git-ignored .env file. A .env.example file without values will be committed.
  At second version of this project, secrets will be moved to OpenBao. First version uses only .env file.
  Project's summary described below:

  -- REPOSITORY --
  - Project is a monorepo. Top level folders:
    /wwwroot: React PWA
    /backend: .NET API, EF Core, Quartz.NET
    /rag: Python FastAPI engine and RAG files
    /infrastructure/test: test scenarios and test results
  - Docker will not be used. Every part runs directly on local machine. Hosting will be decided later.

  -- PWA --
  - It will be PWA app to trigger push notifications.
  - To create PWA, vite will be used. 
  - Web push API will be used to trigger push notification.
  - App icon is at /fuxi.jpeg location. The page background is the icon's background colour, #FCFAEE. The header shows the FuXi lettering as tall as the menu button.
  - manifest.webmanifest file will be created. It's content will be defined with agent harness.

  -- Push notification --
  - The application will send push notifications at specific intervals.
  - Push notification will open app. Page will show flashcard carousel.
  - Push notification will be fired only inside Notification Windows. Notification Windows will be defined at schedule page.
  

  -- RAG --
  - There will be content related with word at backside of flashcard.
  - Content will be created using RAG.
  - RAG resources will be Spotify, Notion, Google Drive, letterboxd - TMDB
  - Connection infos will be delivered during development
  - < RAG purpose >
  - The Settings page has the "Update embeddings" action, which calls the RAG engine's Update_Collections API.
  - RAG technologies will be defined at next parts.

  -- Words --
  - Words will be added to database manually by the Learner. There is no add word page or api.

  Design, Database, API, push notification and RAG part will be at project.

  # DESIGN
  - It will be developed using React and LESS technologies.
  - React project will use Typescript language.
  - All frontend pages will be implemented from Claude Design using /sync-design skill
  - Claude Design will be single source of truth
  - Design should only contains LESS and React codes. 
  - HTML will be created from components. Components should only contains visual content like visual interaction, visibility preference.
  - Logical functions like content api request will be at services.
  - App's dashboard should open Words page. Words page will be described at next parts.

    # DESIGN - ROUTES
    - React Router will be used. The header has the FuXi logo and a menu button at the top right. The menu lists Active Words, Words, Schedule, Configs and Settings. There is no bottom tab bar.
    - /words: Words page. It is default page. An unknown path opens it too.
    - /flashcard: Flashcard carousel page. A notification opens it with wordIds.
    - /active: Active Words page. It shows the same Flashcard carousel, filled with the Due Words.
    - /schedule: Schedule page.
    - /config: Config page. Its title is "Configs".
    - /settings: Settings page.
  
    # DESIGN - API CONNECTION
    API - frontend connections described below. 
    There will be apis with same name as described below. 
    APIs' content will be defined at API part.
    Frontend calls both .NET API and Python FastAPI directly. CORS will be enabled at both APIs.

    -- flashcard --
    - Flashcard page's word data source depends on where user comes from:
      If user comes from notification, word ids will be taken from notification payload's wordIds value and GetCardWords api will be called.
      If user comes from Active Words page, data will be taken by GetWordsByActive api.
    - When user clicks to Yes or No buttons at flashcard component's front side, UpdateWordKnownStatus api will be called and card turns to back side.
    If button text is Yes, isKnown value should be true, if it is no, value should be false.
    - When user opens Word History toggle clicking text and arrow icon at flashcard component's back side, if history is not exists, it should loaded by GetWordHistory api call.
    - When user clicks to reinforcement button next at the top right side of flashcard component's back side, next word should be shown and UpdateIsReinforcement api should be called with true parameter value.
    - After getting card data, GetWordContent api is called with words whose Content value is empty. Its parameter is word names joined with comma. Last, GetWordContent data and card data should be merged by word. Every generated content will be passed to UpdateWordContent api with word id.
    - Back side of card shows a loading state until content arrives. Word Content is shown as plain text. If it cannot be generated, the card says that content is not available.
    - The X button at the top right of the back side is the reinforcement button.
    - On the last card's back side the right arrow is hidden and a Done button opens the Done screen.
    - While user is moving between carousels, user can move forward freely. User can move back, but they can see just back side of card. 
      If user comes last card, right arrow will be hidden and Done screen will be shown.

    -- active words --
    - When user opens Active Words page Frontend should be called GetWordsByActive api. Content flow is same as flashcard's GetWordContent flow.
    - If there is no word to display, "Keep working like this; there are no words to review at the moment." text will be visible.
    
    -- config --
    - When user opens Config page, data should be loaded by GetConfigs api call.
    - When user clicks to Config page's save button (It means saves config), if row's Code value is NotificationPeriod, UpdateNotificationPeriod api should be called.
    If it is not, UpdateConfig should be called.

    -- settings --
    - When user clicks "Update embeddings" and confirms with Yes, Update_Collections api of the RAG engine is called. The result is shown in a dialog.
    - Settings page has "Enable notifications" button under the "Update embeddings" row. Browser asks notification permission only after this button is clicked. Permission state is visible at Settings page.

    -- schedule --
    - When user opens schedule page, data should be loaded by GetSchedule api with current month's start and end date-times.
    - When user selects new Notification Window from schedule, UpdateSchedule api will be called. If user changes an existing Notification Window, its id will be sent too.
    - When user changes visible month GetSchedule api should be called with new month's parameters.
    - The calendar has Month, Week and Day views. GetSchedule is called again only when the view shows dates outside the loaded range.
    - When user edits an existing Notification Window, the dialog has a Delete button that calls DeleteSchedule api.
    - Date-times are sent to backend as UTC.

    -- words --
    - Words page will gets empty at first.
    - When user applies the filter fields, GetWordsByFilter api will be called.
    - When user clicks a word name, its Word History is loaded by GetWordHistory api and shown in a dialog.
    - Columns can be sorted in the browser without a new api call.
    - If there is data, no pagination will be implemented.

  # Database
  This part includes relational database's tables and it's columns.
  InputType value describe below should be enum. Enum options will be CheckboxList, Radiobutton, String, Number, Date.
  Entity Framework will be used to connect PostgreSQL with .NET. Code-first approach will be implemented. So, tables described below.
  Config table's defaults values also described below.  
  All date-time columns are timestamptz and stored as UTC.
  All period values are minutes.


  -- Words --
  Id: Guid, primary_key
  Name: text
  Translation: text
  Content: text
  IsKnown: bool
  IsReinforcement: bool
  ShownCount: number
  KnownCount: number

  -- RotatedWords --
  Id: Guid, primary_key
  WordId: Guid, foreign_key
  LastShownDate: timestamptz, nullable. Null means word is due now.
  Counter: number. New entry starts with 1.

  -- Config --
  Id: Guid, primary_key
  Name: text
  Code: text
  Value: text. It is parsed according to InputType.
  InputType: enum

    Default values of Config table (Name, Code, Value, InputType):
    Rotation Count, RotationCount, 20, number
    Rotation period, RotationPeriod, 15, number
    Reinforcement period, ReinforcementPeriod, 10800, number
    Notification period, NotificationPeriod, 15, number

  -- WordHistory --
  Id: Guid, primary_key
  WordId: Guid, foreign_key
  IsKnown: bool
  Date: timestamptz

  -- Schedule --
  Id: Guid, primary_key
  StartDate: timestamptz
  EndDate: timestamptz

  -- PushSubscription --
  Id: Guid, primary_key
  Endpoint: text
  P256dh: text
  Auth: text
  CreatedDate: timestamptz


  # API
  APIs that will be used at this project described below.
  APIs' triggering place and time describe at DESIGN - API CONNECTION section.

  - GetNotificationWords
    It will gets full date as parameter. Filters data from RotatedWords table.
    If the number of records in the `RotatedWords` table is less than the value specified in the `Value` column of the record in the `Config` table where `Code` is 'RotationCount', then a number of records equal to the difference is added to the `RotatedWords` table. These records are selected randomly from those in the `Words` table for which the `IsKnown` value is `false` or the `IsReinforcement` value is `true`, and which are not already in `RotatedWords`.
    Second, RotatedWords table should be filtered according to below rule. This filtered list are sent formatting as output model. Rule:
    If word's IsReinforcement value is false below formula should be used:
      LastShownDate is null or ((RotatedWords.Counter * RotationPeriod) + RotatedWords.LastShownDate) <= Now
    If this value is true
      LastShownDate is null or (ReinforcementPeriod + RotatedWords.LastShownDate) <= Now
    Output model will be list of Words.Id and Words.Name.
  - GetCardWords
    It gets word ids joined with comma. It splits from comma. This word array are filtered at both RotatedWords and Words tables and merges. Output model should be:
    Words.Id, Words.Name, Words.Translation, RotatedWords.Counter, Words.IsReinforcement, RotatedWords.LastShownDate, Words.Content
  - UpdateWordContent
    It takes id as Guid and content as text. It updates Content column of Words entry that filtered by Id using id value.
  - UpdateWordKnownStatus
    It will gets word id as guid and isKnown as boolean. All steps below run in one transaction.
    RotatedWords entry is filtered by word id. If isKnown is true entry's Counter value will be increased one, it is not Counter will be 1. LastShownDate will be updated to now.
    Words entry is filtered by word id. ShownCount will be increased one. If isKnown is true, KnownCount will be increased one and IsKnown will be true.
    A new WordHistory entry is added with word id, isKnown and now.
    Known words stay at RotatedWords table.
  - GetWordHistory
    It takes word id as Guid. It returns WordHistory entries of the word, newest first. Output model: IsKnown, Date.
  - GetWordsByFilter
    There should be FilterRequest model. It will be consist of Name as text, IsReinforcement and IsKnown as boolean. These 3 fields should be used to filter from Words table. Last field is IsRotated and it will be boolean. It will filter from RotatedWords table. 
    Empty filter field means any value.
    Words table and RotatedWords table will be joined using left join.
    IsRotated field will be added to filtered data. This value will be true if this word is exist at RotatedWords table.
    Output model should be Words.Id, Words.Name, Words.IsReinforcement, Words.IsKnown, RotatedWords.LastShownDate, Words.ShownCount, Words.KnownCount, IsRotated, RotatedWords.Counter. Counter is null when the word is not in RotatedWords.
  - GetWordsByActive
    First, it will find word ids with GetNotificationWords function with current date. Second, GetCardWords function should be called using word ids as parameter. Last data should be returned as response. Output model should be same as GetCardWords.
  - GetConfigs
    It gets Config table data. Output model will be ConfigId, Code, Name, Value and InputType
  - GetSchedule
    It gets period as parameter. Period will be date-time array, consist of 2 value.
    Schedule table's data will be filtered by overlap: entries whose StartDate is smaller than second value of period and EndDate is bigger than first value of period.
    Output model: Id, StartDate, EndDate.
  - UpdateSchedule
    It takes optional id, start date-time and end date-time.
    If new Notification Window overlaps another entry, request is rejected.
    If id is not empty, entry with this id is updated. If it is empty, a new entry is added.
  - DeleteSchedule
    It takes id as Guid. It deletes Schedule entry with this id.
  - UpdateIsReinforcement
    It takes isReinforcement boolean value and wordId as Guid. It updates IsReinforcement value of Words entry that filtered by Id using wordId value.
    After updating Words table, the related word's entry is deleted from RotatedWords table.
  - UpdateConfig
    It takes id as Guid and value as text. It updates Value column of Configs entry that filtered by Id using id value.
  - UpdateNotificationPeriod
    First, UpdateConfig function will be ran with id and value parameters. 
    Quartz.NET's timed task is stopped. Started with new interval. New interval should be value parameter in minutes.
  - GetVapidPublicKey
    It returns VAPID public key.
  - SavePushSubscription
    It takes Endpoint, P256dh and Auth. It adds a PushSubscription entry. If endpoint already exists, it is not added again.


  # PUSH NOTIFICATION
  - App will triggers push notification at specific time intervals.
  - This interval will be at Config table. The Value column of the record with a Code value of "NotificationPeriod".
  - When task runs, if date and time is not inside any Notification Window, push notification won't sent. Notification Windows are Schedule table's entries. The time between the StartDate and EndDate in each record is a Notification Window.
  - If GetNotificationWords returns no word, push notification won't sent.
  - If Learner ignores a notification, same words will be sent again at next run.
  - Notification payload: JSON with title and wordIds. Title is word names joined with ", ", wordIds is word ids joined with comma.
  - Notification click opens /flashcard with wordIds. If FuXi is already open in a tab, that tab is focused and moved to /flashcard; otherwise a new window opens.
  - Quartz.NET uses RAM store. Trigger is created from Config at startup. The first run comes one Notification Period after startup or after UpdateNotificationPeriod.
  - A Notification Window contains now when StartDate <= now < EndDate.
  - The timed task does not change Words or RotatedWords.
  - Workflow and order listed below
    Register service worker at main entry script right after page loads
    Learner clicks "Enable notifications" button at Settings page. Ask permission to user for notification
    The setup script runs the backend's generate-vapid-keys command, which creates the VAPID keys with .NET's built-in cryptography. It is done once. Keys and VAPID_SUBJECT (a mailto: or https: contact) are stored at .env file.
    Page will call subscribe() with VAPID public key which will get with GetVapidPublicKey api call, and get back a subscription object.
    Page will send the subscription to backend with SavePushSubscription api, which stores it in a database.
    Quartz.NET will triggers task
    Backend will sign the message with VAPID key using the Lib.Net.Http.WebPush library. Payload is encrypted with aes128gcm, so every browser, Safari included, accepts it.
    Post signed message using PushServiceClient.RequestPushMessageDeliveryAsync function to every subscription's endpoint. If endpoint returns 410 Gone, subscription is deleted. Other failures are logged and the subscription is kept.
    The service worker will wake up and show the notification.
  

  # RAG
  - RAG architecture, models and tools to be used defined below
  - RAG resources will be Spotify, letterboxd, TMDB, Google Drive and Notion

  - There will be python files: resource, base, embedding_pipeline, rag_client, llm_client, engine, evaluation. Every file described separately below
    
    # resource
    - Resources will be developed SOLID principles' open closed principle.
    - Ask me about any gaps or requirements in the processes of connecting to sources and retrieving data, and we will proceed step by step.

      # NOTION
      - Notion API will be used
      - All data will be taken

      # Google Drive
      - Google Drive API will be used
      - Just images will be taken. Image name, content, date and path
      - Image's itself will be embedded.

      # letterboxd, TMDB
      - letterboxd's api will be used to take watched movies
      - Movies will be filtered using TMDB's ... api by data taken from letterboxd. Filter fields will be name and year.
      - Watched list will be taken from letterboxd with letterboxd's API
      - Watched movies' name, director, musician, scriptwriter, genre, summary and actors info will be taken from TMDB

      # Spotify
      - Liked song playlist will be taken from Spotify's Web API.
      - Song will include musician and song name.

    # embedding_pipeline
    - It will be convert resources' data to embed
    - There will be model argument of this file. These are create and update embedding processes
    - When user opens app, system will check, if there is not embedding data, it will create. 
    - If user wants to update embedding, engine runs and it triggers update embedding pipeline from this file.
    - ChromaDB will be used for vector embedding database
    - ChromaDB will use HNSW indexing
    - All steps will be logged manually to text file. It will be under /logs/embedding path with yyyy_MM_dd_mm_hh date formatted file name.
    - If data is image. Image's embeds will be stored second collection.
    - Plain data will be used as one of the parameter while adding to collection. If data is image, image will be converted to Base64 and it will be used as collection's data.
    - Every resource types will be own model and function but pipeline - workflow will be same.
    - Workflow described as below:
      + If mode is create:
        - Data will be looped according to batch_size.
        - Id will be generated as guid. It will be unique.
        - New model will be created using id, data and metadata.
        - Embedding will be created from model using resource's own llm model.
        - Every record's id, embedding, metadata info will be add to separate arrays.
        - Collection will be added to ChromaDB as ids, data as texts, embeddings as embeddings, metadatas.
      + If mode is update:
        - All collections will be deleted
        - Mode create will be ran
    - Every resource types properties described as below:
      + Google Drive
        metadata: {
          name,
          path,
          type: picture,
          timestamp
        }
        chunk type: Per image
        chunk tool / transformer: Hugging Face's CLIP
      + Spotify
        metadata: {
          name,
          musician,
          album
          type: song,
          timestamp
        }
        chunk type: per song. One document per song, no splitter.
        transformer: Qwen3-Embedding-0.6B
      + letterboxd, TMDB
        metadata: {
          name,
          director, 
          musician,
          genre,
          timestamp,
          type: text
        }
        chunk type: per movie. One document per movie, no splitter.
        transformer: Qwen3-Embedding-0.6B
      + Notion
        metadata: {
          name,
          path,
          type: text,
          timestamp
        }
        chunk type: per note. Only long notes are split.
        chunk tool: LangChainTextSplitter
        transformer: Qwen3-Embedding-0.6B

    # rag_client
      - Functions described as below
        + init
          It will cache ChromaDB collection.
          So, there will be Singleton object which is called collection.
        + retrieve
          It will take word as parameter
          It will use below methodologies to get better result
            top_k: 20
            similarity threshold: 0.9
          Replace the part written as {{word}} in the prompt specified below with a word's value.
          /prompts/retrieval.txt file's content will be used as prompt.
          Prompt will be embedded twice:
            Text collection: sentence-transformers library and Qwen3-Embedding-0.6B.
            Image collection: CLIP's text encoder.
          Using singleton collection object's query method with each embedded query, it will get related data
          It will retrieve embeds from both image (CLIP's), text (Qwen's) collection. It will return 2 collections.

        + generate
          It will take words as parameter
          Spit words from comma
          Using loop, it will sends word to retrieve function
          It will create response returning data (2 collections) from retrieve function using llm_client's generate function

    # llm_client
    - File will be use to create response of RAG system
    - It will consist of only generate function
    - Response methods will be story, picture, quote, music, movie reference.
    - Response method will be chosen randomly.
    - Response will create using Google AI Studio API and gemini-3.8-flash model. Model name and search tool name will be verified with current Gemini docs before coding.
    - Model will keep as parameter
    - If response method is picture or music, /prompts/llm_web.txt file's content will be used as prompt and google_search_retrieval tool will be added to tools option of Google AI Studio API. 
      If it is not, /prompts/llm.txt file's content will be used.


    # evaluation
    - It will be second version of this project. So, details will be described later.
    - It will be evaluate generate results.
    - It will contains ragas and custom metrics.
    - It will use ragas library for base metrics.


    # engine
    - There will be API both .NET and python. This file will keep python api's created by fastapi. 
    - APIs listed as below
      + GetWordContent
        It will take words joined with comma as parameter
        It will get response of rag_client's generate function. Words parameter will be used parameter for this function
      + Init_RAG
        It will call embedding_pipeline with mode create argument
        It will trigger rag_client.init function
      + Update_Collections
        It will trigger embedding_pipeline with mode update argument
        It will update rag_client's Singleton collection object


  # TEST
  - Test Driven Development will be used. Workflow is at /standards/workflow.md.
  - Test frameworks:
    .NET: xUnit and FluentAssertions
    Frontend: Vitest and React Testing Library
    Python: pytest
  - Database tests use a separate local PostgreSQL test database. It is recreated before test run.
  - Time based rules are tested with a fake clock (.NET TimeProvider).
  - External APIs and Gemini are tested with recorded responses. Live API tests run only when enabled.
  - Test scenarios are saved at /infrastructure/test/scenarios. Test results are saved at /infrastructure/test/results.
  - Test configs are kept at separate env files.
  - Code quality is checked with Claude Code's built-in code review.
