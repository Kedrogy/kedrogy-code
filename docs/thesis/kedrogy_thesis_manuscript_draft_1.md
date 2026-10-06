# Web integration of the NLP model lifecycle in Kedrogy

Milla Fedotova\
Thesis Manuscript Draft 1\
2026

## 1 Introduction

Kedrogy is a collaborative software prototype that connects data preparation, text annotation, model training, model storage and prediction services. This thesis examines the integration of a React web application and a Prodigy annotation workflow into that system for natural language processing (NLP). Its central concern is how application interfaces can coordinate specialised components while keeping their data, model identities and operation states consistent.

OpenAI Codex assisted with the organisation, drafting and language editing of this chapter and with locating sources. The use of artificial intelligence (AI) in preparing this manuscript is recorded in Appendix 1, Table 3.

### 1.1 Background

A text classification model assigns predefined categories to text. Creating an application around such a model requires decisions that extend beyond the learning algorithm. Source records must be prepared, annotations must be interpreted consistently, and training must produce a saved model package, or artifact, that a prediction service can load. The application must also explain whether these operations are waiting, running, completed or unsuccessful. A failure at one interface can prevent later stages from using an otherwise valid result.

Machine learning (ML) operations, or MLOps, provides a framework for considering these responsibilities together. Kreuzberger, Kühl and Hirschl (2023) describe MLOps through principles, technical components and organisational roles, including workflow orchestration, versioning, testing and reproducibility. This perspective is relevant to Kedrogy because its components participate in a shared lifecycle even though they execute different kinds of work.

Integration creates maintenance obligations of its own. Sculley et al. (2015) identify data dependencies, configuration and surrounding software infrastructure as sources of technical debt in ML systems. A change to a label definition, for example, may affect both training and the interpretation of a prediction. The thesis therefore treats the interfaces between components as a software engineering problem that warrants documentation and evaluation.

### 1.2 Project context

The Kedrogy project originated from company-based practical training. It combines a Django application and a React single-page application connected through an application programming interface (API). The API uses Representational State Transfer (REST) conventions. Kedro organises data preparation and training pipelines, Prodigy provides the annotation interface, and Hugging Face Transformers supplies the model training functionality. Kubernetes executes the relevant workloads, PostgreSQL stores application and annotation records, and a FastAPI service exposes predictions from a saved model.

These components have separate responsibilities. Django receives lifecycle requests and maintains application records. Background workers and reconciliation processes coordinate longer operations. Kedro defines processing dependencies within pipelines, whereas Kubernetes manages the workloads that execute them. React presents the controls and status information through which users interact with this arrangement. The project documents describe the overall design and its intended workflow (Fedotova 2026a; Fedotova 2026b).

The workflow includes preparation outside the main web interface. Source registration and ingestion use administrative or command-line operations and explicitly selected pipelines (Kedrogy contributors 2026). Once the relevant records exist, application controls connect annotation, training, serving and prediction activities. Creating an application dataset record is consequently different from importing the underlying source data. This distinction defines the extent of web integration examined in the thesis.

### 1.3 Problem statement

The integration problem concerns the relationship between a user's action and the operation that eventually implements it. A Hypertext Transfer Protocol (HTTP) response can acknowledge a training request before a training workload has started. A workload can finish without producing a compatible checkpoint. A prediction service can respond successfully while using a model whose classification quality is inadequate for its intended task. Each event has a different meaning and requires appropriate evidence.

The application must preserve these distinctions while linking the stages together. Relevant questions include whether annotations belong to the selected dataset, whether training uses the intended class mapping, and whether a prediction comes from the selected model revision. Status reporting must also remain meaningful when requests are repeated or an external workload fails. The practical problem is to connect these responsibilities through understandable interfaces and explicit data exchanges.

### 1.4 Scope and individual contribution

My contribution covered React application structure, routes, dataset and model pages, forms, translations, API communication and the presentation of task status. My backend contribution included Django REST API endpoints connecting the frontend to dataset and model operations and task-status reporting. I was responsible for integrating Prodigy into the project and connecting access to its annotation workflow with the application. This responsibility concerned the connection between the existing annotation tool and the surrounding system; Prodigy's annotation interface was not developed from scratch as part of my React work.

The core data and training pipelines, Kubernetes execution mechanisms and prediction-service foundations included work by other contributors. The current prototype also contains collaborative refinements. Describing those components is necessary to explain the interfaces used by my work, but does not establish individual authorship of their complete implementation. The thesis distinguishes the application integration from the pre-existing platform and subsequent work whose individual ownership is not established.

The study concerns the implemented prototype and its documented environment. Implementation descriptions refer to the archived source snapshot captured on 3 October 2026, including working-copy changes (Kedrogy contributors 2026). The scope covers workflow integration; new model architectures, training from first principles and production readiness are outside it. Predictive quality, including performance across languages, remains a separate property requiring appropriate data and measurements.

### 1.5 Thesis structure

Chapter 2 defines the objective, development objectives and research questions. Chapter 3 establishes the theoretical concepts used to analyse the integration. The subsequent practical chapters will describe the architecture and individual implementation contribution, present the validation evidence, and discuss the findings and limitations. The present manuscript contains the introduction, objectives, theoretical background and references for the first draft.

## 2 Objectives and research questions

The objective of this thesis is to document and evaluate the integration of a web application and Prodigy annotation workflow into Kedrogy's orchestrated NLP lifecycle. The focus is the relationship between user-facing operations and the existing data, annotation, training and serving components. OpenAI Codex assisted with the structure and wording of this chapter; the assistance is documented in Appendix 1.

### 2.1 Development objectives

The application development objectives were to provide navigable dataset and model views, connect their forms and actions to Django REST API operations, and present progress and errors for tasks that continue after a request returns. These objectives link interface behaviour to backend responsibilities: a visible button must correspond to a valid operation, and the subsequent status must describe that operation rather than merely the success of the initial request.

A further objective was to integrate Prodigy with the project so that users could enter the appropriate annotation workflow from the application. This required relating the application dataset to the annotation context and preserving the distinction between application controls and Prodigy's own labelling interface. The annotation output then had to remain usable by the existing training workflow.

The thesis extends this work through architecture documentation, interface analysis and examination of validation evidence. It distinguishes individual implementation from pre-existing and collaborative components, evaluating their connections without attributing the whole platform to one developer.

### 2.2 Research questions

The study addresses three research questions. RQ1 examines the integration structure, RQ2 examines continuity across operations, and RQ3 examines the practical consequences of the architecture. Table 1 identifies the evidence relevant to each question.

Table 1. Research questions and relevant evidence

| Research question | Evidence needed |
| --- | --- |
| RQ1 How can a web application connect user actions to an orchestrated NLP lifecycle? | Architecture and data-flow descriptions; React and REST API interactions; a trace from an application action to its workload. |
| RQ2 How does the workflow preserve data, labels and model identity in the selected execution and recovery scenarios? | Annotation and training records; class mappings; artifact and serving identities; selected repetition and failure scenarios. |
| RQ3 What benefits and limitations does this architecture present for workflow management and maintenance? | Observations of task status and manual steps; configuration dependencies; recorded defects and architectural trade-offs. |

The questions are related but require different conclusions. A successful execution trace can show that components are connected. It does not establish behaviour under every retry or prove that the architecture improves maintenance effort. Claims about reliability and benefits must be limited to the scenarios and observations actually examined.

### 2.3 Evaluation approach and boundaries

The evaluation will combine repository inspection with selected workflow scenarios. For each scenario, the practical chapter will record the inputs, environment, expected outcome, observed outcome and supporting records. Architecture and execution traces will address RQ1; identity checks and repetition or failure scenarios will address RQ2. For RQ3, the analysis will examine manual steps, status information and configuration dependencies to identify operational benefits and maintenance limitations within this case.

The evaluation distinguishes workflow completion, information continuity and operational visibility. Completion concerns whether an operation reaches its intended outcome. Information continuity concerns whether the expected data, class schema and model identity are retained. Visibility concerns whether the application communicates enough state to explain progress and failure. These criteria provide a consistent basis for examining the research questions.

Software checks and model-quality measurements address different properties. A small training run may be suitable for testing whether a pipeline creates an artifact that a service can load. A predictive evaluation requires labelled examples that are appropriate to the task and a protocol that separates model selection from final testing. Passing recorded integration tests therefore cannot establish a particular classification accuracy or unrestricted reliability in use.

The evidence is bounded by the tested environment, selected scenarios and available records. The study does not include a formal usability experiment, a production load study or an independent comparison of alternative architectures. Statements about ease of use or maintenance will consequently be framed as observations about the workflow and its design, rather than measured improvements for a wider population of users.

## 3 Theoretical background

This chapter explains the concepts needed to understand the application integration and to interpret its validation. Academic literature supports the discussion of ML systems, annotation and evaluation, while official documentation explains the relevant software mechanisms. The links to Kedrogy identify why each concept matters to this particular implementation.

OpenAI Codex assisted with identifying sources, drafting explanations and editing language in this chapter. The cited publications and documentation are the underlying references; the assistance is recorded in Appendix 1.

### 3.1 MLOps and ML lifecycle management

An ML lifecycle connects the preparation of inputs with the use of a trained model. For a supervised text classifier, this includes selecting source text, assigning labels, constructing training examples, fitting a model, retaining its artifacts and making predictions available. Operational feedback can lead to corrections in the data or a later training run. The stages have dependencies, but a working application does not necessarily automate every transition.

Kreuzberger et al. (2023) place orchestration, metadata tracking, model storage and serving within a broader MLOps architecture. Orchestration coordinates the execution of dependent activities; storage retains the outputs needed by later activities. These responsibilities are connected through information about which data and configuration produced a particular model. The presence of one component, such as an orchestrator, does not establish the completeness of the overall MLOps process.

Three levels of coordination are relevant to Kedrogy. The application accepts requests and records their state. A pipeline defines processing dependencies inside an operation. The runtime starts and maintains the required workloads. Keeping these levels distinct helps explain failures: a valid application request may encounter a pipeline data error, while a correct pipeline may be unable to obtain a runtime resource.

A useful lifecycle description therefore records both actions and durable outputs. Annotation produces labelled records; training produces a model artifact; serving associates a running endpoint with that artifact. For the application integration, the important question is whether these relationships can be traced from the interface to the stored records. This gives RQ1 an architectural focus and supplies the identity relationships examined in RQ2. Continuous drift monitoring and automated retraining are outside the implemented workflow considered here.

### 3.2 Data engineering and Kedro pipelines

A data pipeline organises transformations into an explicit graph of dependencies, which may branch or join. In Kedro, nodes represent functions with named inputs and outputs, and pipelines combine those nodes. The Data Catalog describes how datasets are loaded and saved, allowing processing code to refer to data by name rather than embedding every storage detail in a function. This separation is reflected in Kedro's pipeline and catalog interfaces (Kedro contributors n.d.a, n.d.b).

This separation makes the boundary between a transformation and its environment visible. A function that prepares annotation examples can be examined independently of the database connection used to obtain them. However, naming a dataset does not make its contents immutable. A repeatable run also needs the relevant source records, configuration and dependency environment to remain identifiable. In Kedrogy, the convert, ingest, load_examples and train pipelines correspond to different operations, rather than one default command that always executes the entire lifecycle (Kedrogy contributors 2026).

Database persistence serves a different purpose from pipeline structure. A relational database retains records and supports transactions that group related updates. PostgreSQL describes transaction isolation in terms of which concurrent changes an operation can observe (PostgreSQL Global Development Group n.d.). A database transaction does not encompass an external Kubernetes workload simply because the application also stores that workload's identifier. A request can therefore create a database record before the external activity succeeds, leaving the application responsible for reconciling the two states.

Data provenance records the origin and processing history of records, including how they were obtained and interpreted. Gebru et al. (2021) propose documenting a dataset's motivation, composition, collection, preprocessing and intended uses. Applied to this case, those concerns distinguish an original source record from an annotation example and a training instance. A source identifier can link records, but it cannot explain the label definition or whether an annotator saw the full text.

The integration must preserve the distinctions between source data, annotation results and model files. PostgreSQL holds records used by the workflow, while saved model weights reside in persistent filesystem storage. Treating these as separate resources helps identify which output a later stage requires and which evidence is needed when a stage fails.

### 3.3 Human in the loop annotation and Prodigy

Supervised learning depends on examples paired with a target label. Human-in-the-loop annotation introduces human judgement into the construction or correction of those targets. The judgement depends on an annotation scheme that explains the classes and the evidence annotators should consider. For text classification, the same sentence can receive different labels if the task definition changes, even when its text remains identical.

Artstein and Poesio (2008) distinguish consistent annotation from the validity of the underlying interpretation. Agreement between annotators can help assess whether a scheme is applied consistently, but agreement alone does not establish that the scheme captures the intended concept. This distinction matters even where no formal agreement study is performed. A stored answer is evidence of a decision; the quality of that decision depends on the task instructions and review process.

Prodigy supports text classification workflows in which annotators assign labels to presented examples. Its interfaces and recipes control how those decisions are collected, and its database interface persists examples and answers (Explosion n.d.a, n.d.b). The integration must interpret the recorded answer according to the actual recipe. An accepted example with one explicit selected class has a different meaning from a rejected suggestion or an ignored example.

Kedrogy's current workflow uses explicit single-label choices for new annotation datasets. Only accepted examples with a valid selected class become training candidates (Kedrogy contributors 2026). Rejecting or skipping an example does not create an implicit OTHER category. Such a category has meaning only when it belongs to the configured class schema and is explicitly selected. This is a data-contract issue: the annotation interface and training pipeline must agree on what counts as a labelled instance.

Connecting Prodigy to a web application also requires contextual continuity. The dataset selected in the application must correspond to the data presented for annotation, and the returned labels must remain associated with the correct source records. A link that opens an annotation page establishes access; preserving dataset identity and label meaning establishes the more substantial integration. These relationships define the part of the annotation workflow relevant to my contribution.

Human involvement does not imply active learning. Active learning requires a strategy for selecting informative examples, often using model predictions (Explosion n.d.b). The workflow examined here can be explained through explicit annotation without claiming that a model chooses the next example. Likewise, providing an annotation tool does not establish independent human review of every stored label. The provenance of a particular annotation set must be described when that set is used in the practical evaluation.

### 3.4 NLP text classification and transformer models

Text classification assigns one or more predefined categories to a text. This study concerns single-label classification, in which each usable training example has one target class. Training uses numerical class identifiers, whereas the interface presents class names. Their association must remain consistent: assigning an output index to a different class name during prediction changes the reported label even when the numerical output is unchanged.

BERT stands for Bidirectional Encoder Representations from Transformers. A Transformer uses attention mechanisms to relate elements of an input sequence. In self-attention, a token's representation is computed using information from other tokens in that sequence. BERT uses a bidirectional encoder, so its representations can incorporate both preceding and following context. It learns through pre-training and can subsequently be fine-tuned for supervised tasks. Devlin et al. (2019) describe this distinction between general pre-training and adaptation using labelled task examples. For sequence classification, an output layer maps the representation to class scores. Kedrogy uses an existing BERT checkpoint as a starting point, so the relevant development problem concerns fine-tuning and integration rather than constructing a new language-model architecture.

Tokenisation converts text into the input representation expected by the model. The tokenizer and model must remain compatible, including their vocabulary and handling of special tokens. Padding permits examples of different lengths to be processed together, while truncation imposes a limit on the text considered. Hugging Face's sequence-classification workflow uses a tokenizer, a classification model and training utilities to connect these steps (Hugging Face n.d.a). These choices affect the information available to the classifier and should be retained with the trained artifact.

Kedrogy currently applies different input-length policies: training truncates at a configured token limit, whereas serving rejects inputs beyond the limit supported by the tokenizer and model (Kedrogy contributors 2026). The practical evaluation will document both policies and examine inputs around their boundaries. Loading the same tokenizer alone does not establish identical handling of long texts.

Evaluation also depends on how examples are divided. Training data support parameter updates. Validation data support choices such as selecting a checkpoint. An independent test set supports an assessment after those choices are fixed. If validation examples are reused to choose and then report the best checkpoint, the resulting score describes that validation procedure. It is not an independent estimate on unseen test data (scikit-learn developers n.d.a).

Accuracy is the proportion of correct predictions. It can conceal poor performance on a minority class when one class dominates the data. For a given class, precision is the proportion of predictions for that class that are correct. Recall is the proportion of actual examples of that class that are retrieved. F1 is their harmonic mean, and macro F1 averages the class-level scores with equal weight. A confusion matrix and class counts help interpret these measures (scikit-learn developers n.d.c). A conventional majority-class baseline selects the most frequent training class and predicts it for every evaluation example (scikit-learn developers n.d.b).

Kedrogy's current quality reporting separates validation metrics from artifact verification (Kedrogy contributors 2026). Its reported majority statistic is the proportion of the most common class in the validation set, rather than the accuracy of a baseline fitted on training labels. This distinction must be retained when interpreting the report. A saved checkpoint can also load successfully while making poor predictions. Multilingual pre-training alone does not establish performance for the project's languages, domains or labels; those claims require task-specific evaluation.

### 3.5 Web applications and REST APIs

The web application connects human decisions to operations performed elsewhere in the system. Its frontend manages the visible interaction, the backend validates requests and maintains application records, and background processing carries out activities that exceed the useful duration of a browser request. Clear boundaries make it possible to reason about which component owns a particular decision and where its outcome should be observed.

React represents an interface as components whose rendering depends on props and state. State records information that changes during interaction, such as form values, a selected model or an outstanding request (Meta Open Source n.d.). In an ML workflow, state also connects a displayed result with the action that produced it. If the input text changes while a prediction request is pending, an earlier response must not silently appear to describe the new input. The application needs a clear association between the submitted text, request and returned result.

Django supplies the server-side model and request-handling structure. Its model layer describes persistent application data, while Django REST framework serializers translate between representations and validate incoming values (Django Software Foundation n.d.; Django REST framework contributors n.d.). Client-side validation can help users correct mistakes early, but the backend remains responsible for accepting or rejecting an operation. A request constructed outside the interface must be subject to the same rules.

Representational State Transfer (REST) describes architectural constraints for networked applications, including a uniform interface and stateless interactions (Fielding 2000, chapter 5). For this thesis, the relevant practical boundary is the HTTP API through which React exchanges structured data with Django. The presence of JSON endpoints does not require claiming that every aspect of the prototype fully satisfies the REST architectural style. What matters to the integration is that requests, responses and error meanings are consistent and documented.

Long-running operations require additional coordination. The API can accept a request, record an operation and return an identifier. Kedrogy uses the third-party django-tasks package and a separate worker process to execute background tasks. Durable run records and reconciliation processes track the external workload, and the status API reads those records where available (Kedrogy contributors 2026). Queue-task completion and lifecycle-operation completion are therefore distinct: a worker can finish its delivery step while the workload still requires observation.

Kedrogy uses polling to obtain updated task information. Polling is understandable for relatively infrequent state changes, but it introduces a delay between a backend transition and its appearance in the browser. The frontend must handle pending, successful and unsuccessful responses without treating a temporary communication problem as proof that the external workload has stopped. Controls should also reflect whether an operation is already in progress, while backend checks prevent conflicting actions regardless of the interface state.

The resulting design connects interface clarity with resource management. Dataset and model pages supply the context, API requests express the intended operation, and persisted operation records support progress reporting. Prodigy remains a specialised annotation application reached through this arrangement. These connections form the main application-level subject of the thesis, while detailed endpoint implementation belongs in the practical chapter.

### 3.6 Containers and Kubernetes orchestration

A container image packages an application and its runtime dependencies; a container is an execution instance of that image (Kubernetes authors n.d.b). Kubernetes manages containerised workloads through resources that describe desired behaviour. A Pod contains one or more containers. The controller type matters because a finite training process and a continuously available prediction service have different lifecycle requirements.

A Kubernetes Job manages work that is expected to terminate, whereas a Deployment maintains a desired set of running application instances. Init containers complete preparation before the main containers start (Kubernetes authors n.d.a, n.d.c, n.d.d). These mechanisms fit different parts of Kedrogy: training and artifact verification are finite activities, while annotation and serving require a running service. Annotation preparation can execute before the annotation interface starts.

Communication and persistence require additional resources. A Service provides a stable way to reach a selected set of Pods. PersistentVolumes and PersistentVolumeClaims separate storage provisioning and requests from the lifetime of an individual Pod (Kubernetes authors n.d.f, n.d.g). A trained checkpoint therefore need not disappear when its training container exits. Nevertheless, durability, access modes and availability depend on the configured storage system; a volume claim alone does not provide backup or unrestricted simultaneous access.

Kubernetes reconciles actual resources with their desired state. The application must interpret what those resource states mean for a user operation. Starting a Pod does not prove that its model is ready to accept requests. A failed readiness probe makes a Pod ineligible for Service traffic, while liveness probes can trigger a container restart (Kubernetes authors n.d.e). These signals support orchestration but do not establish that a model produces correct classifications.

Retries also require application-level care. If an interrupted operation is attempted again, a second attempt may encounter a resource created by the first. The application needs identifiers and ownership rules that make the relationship between requests and resources explicit. In Kedrogy, that relationship links application records to annotation, training and serving workloads. Kubernetes supplies execution mechanisms; the application supplies the meaning of the lifecycle operation and the conditions under which it is considered complete.

### 3.7 Model storage and inference services

A deployable model artifact includes more than its weight tensors. Prediction also depends on model configuration, tokenisation and the mapping from output indices to class names. These items should be stored and loaded as a compatible set. Hugging Face's save and load interfaces support retaining model and tokenizer files for subsequent use (Hugging Face n.d.b, n.d.c). A service that loads different preprocessing or labels from those used during training can produce misleading results despite having readable weight files.

Artifact identity connects training with serving. In Kedrogy, a training run produces files and associated metadata in persistent storage. Verification checks properties such as expected identity, class mappings, file integrity and the ability to execute an offline forward pass (Kedrogy contributors 2026). Serving selects an artifact and exposes it through a separately managed workload. These stages provide different evidence: creation shows that files were produced, verification checks compatibility and integrity, and readiness shows that the service can accept the relevant requests.

FastAPI supports typed request bodies and validation through Pydantic models. Its lifespan mechanism provides a place to initialise a shared resource before requests are served and release it during shutdown (FastAPI contributors n.d.a, n.d.b). Loading a model during startup avoids making every prediction request responsible for repeating model initialisation. A request can then supply text, and the service can return a result expressed in the configured class schema.

Inference is the use of a trained model to compute an output for a new input. To interpret the response, the application should know which model and serving revision produced it. This is especially relevant if a model is retrained while older requests are still in progress. Preserving revision identity makes a result traceable and helps prevent an interface from presenting a response under the wrong model context.

Availability, integrity and predictive usefulness remain distinct. An endpoint can be reachable and its artifact intact while its predictions are unsuitable for a particular language or domain. This separation prevents a successful deployment from being used as evidence for an unsupported accuracy claim. It also gives the practical evaluation a clear order: establish what was served, show that it can be called correctly, and then interpret quality measurements under their own evaluation protocol.

### 3.8 Integration reliability and testing

Integration reliability concerns whether components continue to exchange the intended information under the conditions examined. A unit-level check can verify a label conversion or a response parser. An integration check examines an interaction, such as retrieving accepted annotations and producing training inputs. An end-to-end scenario follows a longer route through the application and its external workloads. Each provides a different view of failure and should be reported with its scope.

Breck et al. (2017) treat testing of data, model-related code and infrastructure as complementary responsibilities. Their discussion includes testing a complete training pipeline with a small dataset or a simpler model to obtain fast feedback. Such a run can reveal interface and configuration errors without establishing the predictive quality of the intended model. This supports using small workflow checks in an integration study, provided their purpose and limits are stated.

Repeated requests, failed workloads and temporarily unavailable services expose different integration failures. Each scenario needs an expected outcome, such as identifying an already active operation or retaining an understandable failure state. Idempotency means that repeating an action has the same intended effect as applying it once. This property is useful for reasoning about retries, but must be assessed for the operation concerned.

Pineau et al. (2021) emphasise reporting experimental procedures and making the relevant data and code available. Here, repeatability means executing a defined workflow again under documented conditions and tracing its outcomes. This requires recorded inputs, configuration and execution details, without implying that retraining produces identical parameters across different hardware and software environments.

Table 2 translates the chapter's concepts into observable concerns for the practical evaluation. These are evaluation criteria, not statements that every condition has already been demonstrated.

Table 2. Integration properties and observable evidence

| Property | Evidence to examine |
| --- | --- |
| Data and label continuity | The annotation context, accepted class and training mapping remain associated with the intended source records. |
| Operation state | An accepted request can be followed to progress, completion or a meaningful failure record. |
| Artifact and serving identity | The selected checkpoint, class mapping and model identity are checked, including preprocessing and input-length policies. |
| Recovery and repetition | Selected repeated or interrupted operations have documented, consistent outcomes. |
| Repeatability | Inputs, configuration, relevant versions and execution records are sufficient to explain a repeated run. |
| Workflow management and maintenance | Recorded manual steps, status information and configuration dependencies reveal where integration helps and where intervention remains necessary. |

Together, code review and execution records will support the assessment in Table 2. Conclusions will remain limited to the scenarios examined.

## References

Artstein, R. & Poesio, M. 2008. Inter-coder agreement for computational linguistics. Computational Linguistics 34 (4), 555–596. Available at: [https://doi.org/10.1162/coli.07-034-R2](https://doi.org/10.1162/coli.07-034-R2).

Breck, E., Cai, S., Nielsen, E., Salib, M. & Sculley, D. 2017. The ML Test Score: A rubric for ML production readiness and technical debt reduction. 2017 IEEE International Conference on Big Data. Available at: [https://doi.org/10.1109/BigData.2017.8258038](https://doi.org/10.1109/BigData.2017.8258038).

Devlin, J., Chang, M.-W., Lee, K. & Toutanova, K. 2019. BERT: Pre-training of deep bidirectional transformers for language understanding. Proceedings of NAACL-HLT 2019, Volume 1, 4171–4186. Association for Computational Linguistics. Available at: [https://doi.org/10.18653/v1/N19-1423](https://doi.org/10.18653/v1/N19-1423).

Django REST framework contributors. n.d. Serializers. WWW document. Available at: [https://www.django-rest-framework.org/api-guide/serializers/](https://www.django-rest-framework.org/api-guide/serializers/) [Accessed 3 October 2026].

Django Software Foundation. n.d. Django at a glance. Django 6.0 documentation. WWW document. Available at: [https://docs.djangoproject.com/en/6.0/intro/overview/](https://docs.djangoproject.com/en/6.0/intro/overview/) [Accessed 3 October 2026].

Explosion. n.d.a. Database. Prodigy documentation. WWW document. Available at: [https://prodi.gy/docs/api-database](https://prodi.gy/docs/api-database) [Accessed 3 October 2026].

Explosion. n.d.b. Text classification. Prodigy documentation. WWW document. Available at: [https://prodi.gy/docs/text-classification](https://prodi.gy/docs/text-classification) [Accessed 3 October 2026].

FastAPI contributors. n.d.a. Lifespan events. WWW document. Available at: [https://fastapi.tiangolo.com/advanced/events/](https://fastapi.tiangolo.com/advanced/events/) [Accessed 3 October 2026].

FastAPI contributors. n.d.b. Request body. WWW document. Available at: [https://fastapi.tiangolo.com/tutorial/body/](https://fastapi.tiangolo.com/tutorial/body/) [Accessed 3 October 2026].

Fedotova, M. 2026a. Thesis project: Design and implementation of a Kubernetes-orchestrated platform for the lifecycle management of NLP text classification models. Unpublished project overview.

Fedotova, M. 2026b. Thesis project plan: Design and implementation of a Kubernetes-orchestrated workflow for NLP model lifecycle management. Unpublished project plan.

Fielding, R. T. 2000. Architectural styles and the design of network-based software architectures. University of California, Irvine. Doctoral dissertation. Chapter 5. Available at: [https://ics.uci.edu/~fielding/pubs/dissertation/rest_arch_style.htm](https://ics.uci.edu/~fielding/pubs/dissertation/rest_arch_style.htm) [Accessed 3 October 2026].

Gebru, T., Morgenstern, J., Vecchione, B., Vaughan, J. W., Wallach, H., Daumé III, H. & Crawford, K. 2021. Datasheets for datasets. Communications of the ACM 64 (12), 86–92. Available at: [https://doi.org/10.1145/3458723](https://doi.org/10.1145/3458723).

Hugging Face. n.d.a. Fine-tuning. Transformers 4.57.1 documentation. WWW document. Available at: [https://huggingface.co/docs/transformers/v4.57.1/en/training](https://huggingface.co/docs/transformers/v4.57.1/en/training) [Accessed 3 October 2026].

Hugging Face. n.d.b. Models. Transformers 4.57.1 documentation. WWW document. Available at: [https://huggingface.co/docs/transformers/v4.57.1/en/main_classes/model](https://huggingface.co/docs/transformers/v4.57.1/en/main_classes/model) [Accessed 3 October 2026].

Hugging Face. n.d.c. Tokenizer. Transformers 4.57.1 documentation. WWW document. Available at: [https://huggingface.co/docs/transformers/v4.57.1/main_classes/tokenizer](https://huggingface.co/docs/transformers/v4.57.1/main_classes/tokenizer) [Accessed 3 October 2026].

Kedro contributors. n.d.a. Kedro data catalog. Kedro 1.2.0 documentation. WWW document. Available at: [https://docs.kedro.org/en/1.2.0/catalog-data/data_catalog/](https://docs.kedro.org/en/1.2.0/catalog-data/data_catalog/) [Accessed 3 October 2026].

Kedro contributors. n.d.b. Pipeline object. Kedro 1.2.0 documentation. WWW document. Available at: [https://docs.kedro.org/en/1.2.0/build/pipeline_introduction/](https://docs.kedro.org/en/1.2.0/build/pipeline_introduction/) [Accessed 3 October 2026].

Kedrogy contributors. 2026. Kedrogy source evidence for Thesis Manuscript Draft 1. Snapshot KG-D1-20261003-bf7be2e9a17b, captured 3 October 2026. Selected source files and technical documentation, including working-copy changes based on commit bcfde46. ZIP archive with a file manifest and SHA-256 checksums, held by the author in the thesis evidence folder and available to the supervisor.

Kreuzberger, D., Kühl, N. & Hirschl, S. 2023. Machine learning operations (MLOps): Overview, definition, and architecture. IEEE Access 11, 31866–31879. Available at: [https://doi.org/10.1109/ACCESS.2023.3262138](https://doi.org/10.1109/ACCESS.2023.3262138).

Kubernetes authors. n.d.a. Deployments. WWW document. Available at: [https://kubernetes.io/docs/concepts/workloads/controllers/deployment/](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) [Accessed 3 October 2026].

Kubernetes authors. n.d.b. Images. WWW document. Available at: [https://kubernetes.io/docs/concepts/containers/images/](https://kubernetes.io/docs/concepts/containers/images/) [Accessed 3 October 2026].

Kubernetes authors. n.d.c. Init containers. WWW document. Available at: [https://kubernetes.io/docs/concepts/workloads/pods/init-containers/](https://kubernetes.io/docs/concepts/workloads/pods/init-containers/) [Accessed 3 October 2026].

Kubernetes authors. n.d.d. Jobs. WWW document. Available at: [https://kubernetes.io/docs/concepts/workloads/controllers/job/](https://kubernetes.io/docs/concepts/workloads/controllers/job/) [Accessed 3 October 2026].

Kubernetes authors. n.d.e. Liveness, readiness, and startup probes. WWW document. Available at: [https://kubernetes.io/docs/concepts/workloads/pods/probes/](https://kubernetes.io/docs/concepts/workloads/pods/probes/) [Accessed 3 October 2026].

Kubernetes authors. n.d.f. Persistent volumes. WWW document. Available at: [https://kubernetes.io/docs/concepts/storage/persistent-volumes/](https://kubernetes.io/docs/concepts/storage/persistent-volumes/) [Accessed 3 October 2026].

Kubernetes authors. n.d.g. Service. WWW document. Available at: [https://kubernetes.io/docs/concepts/services-networking/service/](https://kubernetes.io/docs/concepts/services-networking/service/) [Accessed 3 October 2026].

Meta Open Source. n.d. Managing state. React documentation. WWW document. Available at: [https://react.dev/learn/managing-state](https://react.dev/learn/managing-state) [Accessed 3 October 2026].

Pineau, J., Vincent-Lamarre, P., Sinha, K., Larivière, V., Beygelzimer, A., d'Alché-Buc, F., Fox, E. & Larochelle, H. 2021. Improving reproducibility in machine learning research (a report from the NeurIPS 2019 Reproducibility Program). Journal of Machine Learning Research 22 (164), 1–20. Available at: [https://jmlr.org/papers/v22/20-303.html](https://jmlr.org/papers/v22/20-303.html).

PostgreSQL Global Development Group. n.d. Transaction isolation. PostgreSQL 18 documentation. WWW document. Available at: [https://www.postgresql.org/docs/18/transaction-iso.html](https://www.postgresql.org/docs/18/transaction-iso.html) [Accessed 3 October 2026].

scikit-learn developers. n.d.a. Cross-validation: Evaluating estimator performance. WWW document. Available at: [https://scikit-learn.org/stable/modules/cross_validation.html](https://scikit-learn.org/stable/modules/cross_validation.html) [Accessed 3 October 2026].

scikit-learn developers. n.d.b. DummyClassifier. WWW document. Available at: [https://scikit-learn.org/stable/modules/generated/sklearn.dummy.DummyClassifier.html](https://scikit-learn.org/stable/modules/generated/sklearn.dummy.DummyClassifier.html) [Accessed 3 October 2026].

scikit-learn developers. n.d.c. Metrics and scoring: Quantifying the quality of predictions. WWW document. Available at: [https://scikit-learn.org/stable/modules/model_evaluation.html](https://scikit-learn.org/stable/modules/model_evaluation.html) [Accessed 3 October 2026].

Sculley, D., Holt, G., Golovin, D., Davydov, E., Phillips, T., Ebner, D., Chaudhary, V., Young, M., Crespo, J.-F. & Dennison, D. 2015. Hidden technical debt in machine learning systems. Advances in Neural Information Processing Systems 28, 2503–2511. Available at: [https://proceedings.neurips.cc/paper_files/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html](https://proceedings.neurips.cc/paper_files/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html) [Accessed 3 October 2026].

## Appendix 1 Description of the use of AI

OpenAI Codex assisted in preparing this first manuscript draft. Its work included organising the chapters, reading supplied project documents and repository files, locating primary publications and official documentation, drafting English prose, and preparing the Word document. This appendix records the assistance used for this draft; it does not establish the extent of AI use in earlier implementation work.

Drafting used OpenAI Codex with GPT-6; an independent review also used GPT-6-astra. Table 3 records English translations or concise summaries of the instructions, identified as such rather than presented as verbatim quotations. Two independent reviews began with fresh contexts and examined the entire draft. No software tests, interviews, annotation studies or predictive experiments were carried out during manuscript preparation. Responsibility for reviewing the manuscript and approving its claims remains with the author.

Table 3. Description of the use of AI

| Sections | Purpose | AI tool and model | Prompt and follow-up instructions | Use of the output |
| --- | --- | --- | --- | --- |
| Chapters 1 and 2 | Scope and writing structure | OpenAI Codex with GPT-6 | Translation and summary: Prepare a writing plan for Thesis Manuscript Draft 1 covering Introduction, Objectives, Theory and References. Use the existing project documents. | The project scope, objectives and research questions were organised into manuscript sections. |
| Chapter 3 and References | Source discovery and technical checks | OpenAI Codex with GPT-6 | Summary of the approved plan: Check the repository, use relevant academic and official technical sources, and distinguish individual work from existing and collaborative components. | Sources and code were inspected to support the draft. Citations refer to the publications and documentation rather than to AI as an authority. |
| Chapters 1 to 3 and References | Drafting and independent review | OpenAI Codex with GPT-6 and GPT-6-astra | Translation and summary: Execute the plan carefully and write in English. Follow-up: Review the entire document twice with fresh contexts, checking details and logical connections. | AI generated and revised substantive prose and performed two independent reviews. The author must review the text and claims before submission. |
| Whole document | Formatting and document preparation | OpenAI Codex with GPT-6 | Verbatim follow-up: yes use this template!!! | The supplied Xamk template was used to prepare the manuscript, contents and disclosure appendix. |
