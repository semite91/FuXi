This file is initializer instructor of my project. 

# CONSTRUCTOR
- This is ai first and ai native project.
- An ai first development environment will help to develop this project.
- Ai-first development will be carried out using Claude Code agent harness.
- Project name will be FuXi.

# CONTENT
  This project is customized flashcard app. It is designed to enhance english vocabulary. 
  PostgreSQL will be used for relational database.
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

  Project will be 5 part.

  # DESIGN
  - It will be developed using React and LESS technologies.
  - React project will use Typescript language.
  - Design will be implemented from Claude Design using /sync-design skill
  - It should be 100% same
  - Design should only contains LESS and React codes. 
  - HTML will be created from components. Components should only contains visual content.
  - Logical functions will be at services.
  - App's dashboard should open Words page. Words page will be described at next parts.
  
    # DESIGN - API CONNECTION
    API - frontend connections described below. 
    There will be apis with same name as described below. 
    APIs' content will be defined at API part.

    -- flashcard --
    - When user clicks to Yes or No buttons at flashcard component's front side. UpdateWordKnownStatus api will be called.
    If button text is Yes, isKnown value should be true, if it is no, value should be false.
    - When user opens Word History toggle clicking text and arrow icon at flashcard component's back side, if history is not exists, it should loaded by GetWrdHistory api call.
    - When user clicks to reinforcement button next at the top right side of flashcard component's back side, next word should be shown and UpdateIsReinforcement api should be called with true parameter value.
    - While opening flashcard component. Frontend should be called GetCardWords api with wordIds. wordIds will be taken from push notification payload's wordIds value. After getting data, GetWordContent data with array that contains wordId and name fields. This array should be created from GetCardWords' response filtering if Content value is empty. Last, GetWordContent data and GetCardWords data should be merged. The data obtained from GetWordContent will be passed as a parameter to UpdateWordContent when it is called.

    -- active words --
    - When user opens Active Words page Frontend should be called GetWordsByActive api. After getting data, GetWordContent data with array that contains wordId and name fields. This array should be created from GetCardWords' response filtering if Content value is empty. Last, GetWordContent data and GetCardWords data should be merged. The data obtained from GetWordContent will be passed as a parameter to UpdateWordContent when it is called.
    
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

  # Database
  This part includes relational database's tables and it's columns.
  InputType value describe below should be enum. Enum options will be CheckboxList, Radiobutton, String, Number, Date

  -- Words --
  Id: Guid
  Name: text
  Translation: text
  IsKnown: bool
  ShownCount: number

  -- RotatedWords --
  Id: Guid
  IsReinforcement: bool
  LastShownDate: Date
  Counter: number

  -- Config --
  Id: Guid
  Name: text
  Code: text
  InputType: enum

  -- WordHistory --
  Id: Guid
  WordId: Guid
  IsKnown: bool
  Date: Date


  # API
  APIs that will be used at this project described below.
  APIs' triggering place and time describe at DESIGN - API CONNECTION section.

  - GetNotificationWords
    It will gets full date as parameter. Filters data from RotatedWords table.
    First, if RotatedWords table's entry count is below Config table's RotationCode Coded entry's value. Remaining entries should be selected randomly from Words table that IsKnown value is false. This list's name should be newWords.
    Second, RotatedWords table should be filtered according to below rule:
    If record's IsReinforcement value is false below formula should be used:
      RotatedWords.Counter * RotationPeriod + RotatedWords.LastShownDate <= Now
    If this value is true
      ReinforcementPeriod * RotatedWords.LastShownDate <= Now
  - GetCardWords
    It gets wordIds joined with comma. It splits from comma. This word array are filtered at both RotatedWords and Words tables and merges. Output model should be:
    WordId, Name, Translation, Counter, IsReinforcement, LastShownDate, Content
  - UpdateWordKnownStatus
    It will gets wordId as guid and isKnown as boolean. Entry will be filtered at RotatedWords table by wordId. 
    If isKnown is true entry's Counter value will be increased one, it is not Counter will be 1.
    Entry will be filtered at RotatedWords table by wordId. 
     This entry's LastShownDate will be updated to now. ShownCounter will be increased one. If isKnown is true, KnownCount will be increased one.
  - Update
  - GetWordsByFilter
    There should be FilterRequest model. It will be consist of Name as text, IsReinforcement and IsKnown as boolean. These 3 fields should be used to filter from Words table. Last filed is IsRotated and it will be boolean. It will filter from RotatedWords table. Words table's and RotatedWords table's filtered data will be joined using inner join.
    Output model should be Name, IsReinforcement, IsKnown, LastShownDate, ShownCount, KnownCount, IsRotated.
    IsRotated will be true if record is exists at RotatedWords table.
  - GetWordsByActive
    It should find wordIds with GetNotification function first with current date. Second, GetCardWords function should be called using wordIds as parameter. Last data should be returned as response.
  - GetConfigs
    It gets Config table data. Output model will be ConfigId, Code, Name and Value
  - GetSchedule
    It gets period as parameter. Period will be date array, consist of 2 value.
    Schedule table's data will be filtered by these parameters. Start date should be equal or bigger than first value of period and end date should be equal or smaller than second value of period.
  - UpdateSchedule


  # PUSH NOTIFICATION
  - App will triggers push notification at specific time intervals.
  - This interval will be at Config table. The Value column of the record with a Code value of "Notification Period".
  - Notification content will be words that joined with comma.
  - Workflow and order listed below
    Quartz.NET will triggers task
    Web API project creates data using GetNotificationWords api
    VAPID creates JWT
    Web push api publishes notification
    Service worker takes notification and shows
    When user clicks to notification, service worker will run url of payload and app will open
  

  # RAG
  - RAG architecture, models and tools to be used defined below
  - RAG resources will be Spotify, letterboxd, TMDB, Google Drive and Notion

  - There will be python files: resource, base, embedding_pipeline, rag_client, llm_client, engine, evaluation. Every file described separately below
    
    # resource
    - Resources will be developed SOLID principles' open closed principle.

      # NOTION
      - Notion API will be used
      - All data will be taken

      # Google Drive
      - Google Drive API will be used
      - Just images will be taken. Image name, content, date and path

      # letterboxd, TMDB
      - letterboxd's api will be used to take watched movies
      - Movies will be filtered using TMDB's ... api by data taken from letterboxd. Filter fields will be name and year.
      - Watched list will be taken from letterboxd with letterboxd's API
      - Watched movies' name, director, musician, scriptwriter, genre, summary and actors info will be taken from TMDB

      # Spotify
      - Liked song playlist will be taken from Spotify's Web API.
      - Song will include musician and song name.

    # base
    - It will keep project specific, general needs.

      # TOKENIZATION
      - First part of RAG ecosystem is tokenization
      - Hugging Face's libraries will be used for tokenizations. hugging Face's tokenizer.

    # embedding_pipeline
    - It will be convert resources' data to embed
    - There will be model argument of this file. These are create and update embedding processes
    - When user opens app, system will check, if there is not embedding data, it will create. 
    - If user wants to update embedding, engine runs and it triggers update embedding pipeline from this file.
    - ChormaDB will be used for vector embedding database
    - ChormaDB will use HNSW indexing
    - All steps will be logged manually to text file. It will be under /logs/embedding path with yyyy_MM_dd_mm_hh date formatted file name.
    - Every resource types will be own model and function but pipeline - workflow will be same.
    - Workflow described as below:
      + Tokenizer will be loaded from Hugging Face tokenizer.
      + If mode is create:
        - Data will be looped according to batch_size.
        - Document id will be generated. It will be unique.
        - New model will be created using id, data and metadata.
        - Embedding will be created from model using resource's own llm model.
        - Embeddings of every record will be converted using convert_list_embeddings_to_np function of ChormaDB.
        - Every record's id, embedding, metadata info will be add to separate arrays.
        - Collection will be add to ChormaDB as ids, documents as embeddings, metadatas.
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
          It will cache ChormaDB collection.
          So, there will be Singleton object which is called collection.
        + retrieve
          It will take word as parameter
          Replace the part written as {{word}} in the prompt specified below with a word's value.
          Prompt will be converted to embed using sentence-transformers library and Qwen3-Embedding-0.6B.
          Using singletion collection object's query method with embedded query, it will get related data
          /prompts/retrieval.txt file's content will be used as prompt.

        + generate
          It will take words as parameter
          Spit words from comma
          Using loop, it will sends word to retrieve function
          It will create response returning data from retrieve function using llm_client's generate function

    # llm_client
    - File will be use to create response of RAG system
    - It will consist of only generate function
    - Response methods will be story, picture, quote, music, movie reference.
    - Response method will be chosen randomly.
    - Response will create using Google AI Studio API and gemini-3.8-flash model
    - Model will keep as parameter
    - If response method is image or music, /prompts/llm_web.txt file's content will be used as prompt. 
      If it is not, /prompts/llm.txt file's content will be used.


    # evaluation
    - It will be second version of this project. So, details will be described later.
    - It will be evaluate generate results.
    - It will contains ragas and custom metrics.
    - It will use ragas library for base metrics.


    # engine
    - This file will keep api's created by fastapi
    - APIs listed as below
      + GetWordContent
        It will take words joined with comma as parameter
        It will get response of rag_client's generate function. Words parameter will be used parameter for this function
      + Init_RAG
        It will call embedding_pipeline with mode create argument
        It will trigger rag_client.init function
        After that, 
      + Update_Collections
        It will trigger embedding_pipeline with mode update argument
        It will update rag_client's Singleton collection object