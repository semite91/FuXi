This file is initializer instructor of my project. 

# CONSTRUCTOR
- This is ai first and ai native project.
- An ai first development environment will help to develop this project.
- Ai-first development will be carried out using Claude Code agent harness.
- Project name will be FuXi.

# CONTENT
  This project is customized flashcard app. It is designed to enhance english vocabulary. 
  PostgreSQL will be used for relational database.
  Secrets will be stored at OpenBao account. But it will be at v2.
  Project's summary described below:

  -- PWA --
  - It will be PWA app to trigger push notifications.
  - To create PWA, vite will be used. 
  - Web push API will ve used to trigger push notification.
  - App icon is at /fuxi.jpeg location.
  - manifest.webmanifest file will be created. It's content will be defined with agent harness.

  -- Push notification --
  - The application will send push notifications at specific intervals.
  - Push notification will open app. Page will show flashcard carousel.
  - Push notification will be fired only available times. This time period will be defined at schedule page.
  

  -- RAG --
  - There will be content related with word at backside of flashcard.
  - Content will be created using RAG.
  - RAG resources will be Spotify, Notion, Google Drive, letterboxd - TMDB
  - Connection infos will be delivered during development
  - < RAG purpose >
  - There will be Settings and Configs pages to define project general parameters and settings.
  - RAG technologies will be defined at next parts.

  Design, Database, API, push notification and RAG part will be at project.

  # DESIGN
  - It will be developed using React and LESS technologies.
  - React project will use Typescript language.
  - Design will be implemented from Claude Design using /sync-design skill
  - Claude Design will be single source of truth
  - Design should only contains LESS and React codes. 
  - HTML will be created from components. Components should only contains visual content like visual interaction, visibility preference.
  - Logical functions like content api request will be at services.
  - App's dashboard should open Words page. Words page will be described at next parts.
  
    # DESIGN - API CONNECTION
    API - frontend connections described below. 
    There will be apis with same name as described below. 
    APIs' content will be defined at API part.

    -- flashcard --
    - When user clicks to Yes or No buttons at flashcard component's front side. UpdateWordKnownStatus api will be called.
    If button text is Yes, isKnown value should be true, if it is no, value should be false.
    - When user opens Word History toggle clicking text and arrow icon at flashcard component's back side, if history is not exists, it should loaded by GetWordHistory api call.
    - When user clicks to reinforcement button next at the top right side of flashcard component's back side, next word should be shown and UpdateIsReinforcement api should be called with true parameter value.
    - While opening flashcard component. Frontend should be called GetCardWords api with word ids. Word ids will be taken from push notification payload's wordIds value. After getting data, GetWordContent data with array that contains word dd and name fields. This array should be created from GetCardWords' response filtering if Content value is empty. Last, GetWordContent data and GetCardWords data should be merged. The data obtained from GetWordContent will be passed as a parameter to UpdateWordContent when it is called.
    - While user is moving between carousels, user can move back, but they can see just back side of card. 
      If user comes last card, right arrow will be hidden

    -- active words --
    - When user opens Active Words page Frontend should be called GetWordsByActive api. After getting data, GetWordContent data with array that contains word id and name fields. This array should be created from GetCardWords' response filtering if Content value is empty. Last, GetWordContent data and GetCardWords data should be merged. The data obtained from GetWordContent will be passed as a parameter to UpdateWordContent when it is called.
    - If there is no word to display, "Keep working like this; there are no words to review at the moment." text will be visible.
    
    -- config --
    - When user opens Config page, data should be loaded by GetConfigs api call.
    - When user clicks to Config page's save button (It means saves config), if row's Code value is NotificationPeriod, UpdateNotificationPeriod api should be called.
    If it is not, UpdateConfig should be called.

    -- schedule --
    - When user opens schedule page, data should be loaded by GetSchedule api with current month's start and end dates.
    - When user selects new period from schedule, UpdateSchedule api will be called. If user changed old period, old period value also should be added to api's parameters. New period should be added for every situation as parameter.
    - When user changes period GetSchedule api should be called with new period's parameters.

    -- words --
    - Words page will gets empty at first.
    - When user selects any value from filter fields, GetWordsByFilter api will be called.
    - If there is data, no pagination will be implemented.

  # Database
  This part includes relational database's tables and it's columns.
  InputType value describe below should be enum. Enum options will be CheckboxList, Radiobutton, String, Number, Date.
  Entity Framework will be used to connect PostgreSQL with .NET. Code-first approach will be implemented. So, tables described below.
  Config table's defaults values also described below.  


  -- Words --
  Id: Guid, primary_key
  Name: text
  Translation: text
  IsKnown: bool
  ShownCount: number

  -- RotatedWords --
  Id: Guid, primary_key
  WordId: Guid, foreign_key
  IsReinforcement: bool
  LastShownDate: Date
  Counter: number

  -- Config --
  Id: Guid, primary_key
  Name: text
  Code: text
  InputType: enum

    Default values of Config table:
    Rotation Count, RotationCount, 20, number
    Rotation period, RotationPeriod, 15, number
    Reinforcement period, ReinforcementPeriod, 10800, number

  -- WordHistory --
  Id: Guid, primary_key
  WordId: Guid, foreign_key
  IsKnown: bool
  Date: Date

  -- Schedule --
  Id: Guid, primary_key
  StartDate: Date
  EndDate: Date


  # API
  APIs that will be used at this project described below.
  APIs' triggering place and time describe at DESIGN - API CONNECTION section.

  - GetNotificationWords
    It will gets full date as parameter. Filters data from RotatedWords table.
    If the number of records in the `RotatedWords` table is less than the value specified in the `Value` column of the record in the `Config` table where `Code` is 'RotationCount', then a number of records equal to the difference is added to the `RotatedWords` table. These records are selected randomly from those in the `Words` table for which the `IsKnown` value is `false`.
    Second, RotatedWords table should be filtered according to below rule. This filtered list are sent formatting as output model. Rule:
    If record's IsReinforcement value is false below formula should be used:
      ((RotatedWords.Counter * RotationPeriod) + RotatedWords.LastShownDate) <= Now
    If this value is true
      (ReinforcementPeriod + RotatedWords.LastShownDate) <= Now
    Output model will consist of: Word names joined with comma
  - GetCardWords
    It gets word ids joined with comma. It splits from comma. This word array are filtered at both RotatedWords and Words tables and merges. Output model should be:
    Words.Id, Words.Name, Words.Translation, Words.Counter, Words.IsReinforcement, RotationWords.LastShownDate, Words.Content
  - UpdateWordContent
    It takes id as Guid and content as text. It updates Content column of Words entry that filtered by Id using id value.
  - UpdateWordKnownStatus
    It will gets word id as guid and isKnown as boolean. Entry will be filtered at RotatedWords table by word id. 
    If isKnown is true entry's Counter value will be increased one, it is not Counter will be 1.
    Entry will be filtered at RotatedWords table by word id. 
     This entry's LastShownDate will be updated to now. ShownCounter will be increased one. If isKnown is true, KnownCount will be increased one.
  - GetWordsByFilter
    There should be FilterRequest model. It will be consist of Name as text, IsReinforcement and IsKnown as boolean. These 3 fields should be used to filter from Words table. Last filed is IsRotated and it will be boolean. It will filter from RotatedWords table. 
    First, all filtering process will be done for Words' entries that IsKnown or IsReinforcement value is true. Words table's and RotatedWords table's filtered data will be joined using inner join.
    IsRotated field will be added to filtered data. This value will be true if this word is exist at RotationWords table.
    Output model should will be Words.Name, Words.IsReinforcement, Words.IsKnown, LastShownDate, Words.ShownCount, Words.KnownCount, IsRotated.
  - GetWordsByActive
    First, it will find word ids with GetNotificationWords function with current date. Second, GetCardWords function should be called using word ids as parameter. Last data should be returned as response. Output model should be: Words.Id, Words.Name, Words.Translation, Words.Counter, Words.IsReinforcement, RotationWords.LastShownDate, Words.Content
  - GetConfigs
    It gets Config table data. Output model will be ConfigId, Code, Name and Value
  - GetSchedule
    It gets period as parameter. Period will be date array, consist of 2 value.
    Schedule table's data will be filtered by these parameters. Start date should be equal or bigger than first value of period and end date should be equal or smaller than second value of period.
  - UpdateSchedule
    If old_period parameter is not empty. The record where the StartDate equals old_period[0] and the EndDate equals old_period[1] is deleted. A new record is added where the StartDate is new_period[0] and the EndDate is new_period[1].
  - UpdateIsReinforcement
    It takes isReinforcement boolean value and wordId as Guid. It updates IsReinforcement value of Words entry that filtered by Id using wordId value.
  - UpdateConfig
    It takes id as Guid and value as text. It updates Value column of Configs entry that filtered by Id using id value.
  - UpdateNotificationPeriod
    First, UpdateConfig function will be ran with id and value parameters. 
    Quartz.NET's timed task is stopped. Started with new interval. New interval should be value parameter.


  # PUSH NOTIFICATION
  - App will triggers push notification at specific time intervals.
  - This interval will be at Config table. The Value column of the record with a Code value of "Notification Period".
  - When task runs, if date and time is not between selected times, push notification won't sent. Selected times are Scheduled table's entries. The time remaining between the StartDate and EndDate in each record is the selected time.
  - Notification content will be words that joined with comma.
  - Workflow and order listed below
    Register service worker at main entry script right after page loads
    Ask permission to user for notification
    .NET WebPush API will generate VAPID key. It will done once.
    Page will call subscribe() with VAPID key which will get with api call, and get back a subscription object.
    Page will send the subscription to backend, which stores it in a database.
    Quartz.NET will triggers task
    Backend will sign the message with VAPID ke using WebPush API.
    Post signed message using WebPushClient.SendNotificationAsync function to the subscription's endpoint.
    The service worker will wake ape and show the notification.
  

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
        chunk type: per song
        chunk tool: LangChainSplitter
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
        chunk type: per movie
        chunk tool: LangChainTextSplitter
        transformer: Qwen3-Embedding-0.6B
      + Notion
        metadata: {
          name,
          path,
          type: text,
          timestamp
        }
        chunk type: per note
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
          Prompt will be converted to embed using sentence-transformers library and Qwen3-Embedding-0.6B.
          Using singleton collection object's query method with embedded query, it will get related data
          /prompts/retrieval.txt file's content will be used as prompt.
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
    - Response will create using Google AI Studio API and gemini-3.8-flash model
    - Model will keep as parameter
    - If response method is image or music, /prompts/llm_web.txt file's content will be used as prompt and google_search_retrieval tool will be added to tools option of Google AI Studio API. 
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