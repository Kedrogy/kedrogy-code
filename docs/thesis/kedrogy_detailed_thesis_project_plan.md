# Kedrogy detailed thesis project plan

Web integration and Kubernetes orchestration of the NLP model lifecycle

Milla Fedotova

ITMI23SP

## 1. Introduction and scope

Kedrogy connects data preparation, annotation, training, storage, serving and inference for NLP text classification. This thesis documented and evaluated my web-application and Prodigy integration work within the collaborative prototype. Novel algorithms and production readiness were outside its scope.

## 2. Justification

Coordinating asynchronous ML tools requires consistent data, configuration and status reporting. Kedrogy provided a practical case for examining the integration and maintenance risks discussed by Kreuzberger et al. (2022) and Sculley et al. (2015).

## 3. Objectives and research questions

The objective was to document, refine and evaluate my application integration. The work covered architecture and contribution boundaries, lifecycle controls, normal and failure scenarios, workflow repeatability and limitations.

| Research question | Evidence used to answer it |
| --- | --- |
| RQ1 How can a web application connect user actions to an orchestrated NLP lifecycle? | Architecture and data-flow diagrams; React/API integration; an end-to-end execution trace. |
| RQ2 How reliably does the workflow preserve data, labels and model identity across stages and repeated operations? | Annotation-to-training checks, artifact and prediction identities, repeat runs and selected failure/retry tests. |
| RQ3 What benefits and limitations does this architecture present for workflow management and maintenance? | Task-status observations, manual steps, defect records, configuration dependencies and architectural analysis. |

## 4. Theory

| Proposed topic | Purpose and implementation connection |
| --- | --- |
| 4.1 MLOps and ML lifecycle management | Define lifecycle stages, automation, provenance and reproducibility as criteria for evaluating Kedrogy. |
| 4.2 Data engineering and Kedro pipelines | Explain ingestion, transformations, pipeline dependencies and configuration; relate them to PostgreSQL source data and the convert, ingest, load_examples and train pipelines. |
| 4.3 Human-in-the-loop annotation | Explain supervised labels, annotation quality and traceability. Cover Prodigy's explicit single-label choices and how accepted examples become training data. |
| 4.4 NLP text classification and transformer models | Introduce tokenisation, BERT fine-tuning, class mappings, data splits and classification metrics. Limit the discussion to the implemented Hugging Face workload. |
| 4.5 Containers and Kubernetes orchestration | Explain Jobs, deployments, services, init containers, configuration and persistent volumes as used for annotation, training and serving. |
| 4.6 Web application architecture | Explain React, Django, REST APIs and background processing; connect frontend actions, API validation and status polling to lifecycle operations. |
| 4.7 Model persistence and inference services | Explain checkpoint storage, tokenizer and label compatibility, readiness and FastAPI prediction requests. |
| 4.8 Integration reliability and validation | Explain retries, idempotency, resource ownership and integration testing where these concepts appear in the current implementation. |

## 5. Practical case

### 5.1 Context and architecture

Kedrogy originated from company-based practical training.

| Layer | Existing implementation and responsibility |
| --- | --- |
| Web application | React/TypeScript SPA and Django REST API for dataset/model management, lifecycle actions, predictions and status. |
| Application control | Django records, database-backed background tasks and reconciliation processes coordinate long-running operations and recorded run state. |
| Data and annotation | PostgreSQL holds application, source and annotation data; Kedro prepares examples; Prodigy presents them for human annotation. |
| Training and serving | Hugging Face Transformers performs classification training. Checkpoints persist on Kubernetes storage; FastAPI service loads a selected artifact for inference. |
| Runtime | Kubernetes Jobs execute training and verification; deployments and services support annotation and inference. Local tooling supports the development environment. |

### 5.2 End to end workflow

The validated workflow began with source registration and ingestion through the CLI or a Kedro pipeline. The application connected Prodigy annotation, training in a Kubernetes Job, checkpoint verification, serving and prediction. PostgreSQL stored source and annotation data; persistent volumes retained models. Annotation required explicit accepted class choices.

### 5.3 My individual contribution

| Attribution | Scope and evidence boundary |
| --- | --- |
| My application and Prodigy integration | React pages, forms, navigation, translations and task-status displays; Django REST API communication. I was responsible for integrating Prodigy into the project and connecting its annotation workflow to the web application. |
| Pre-existing project foundation | Core data/training pipelines, Kubernetes execution and prediction-service foundations were developed by other contributors. My work integrated these components with the application and Prodigy workflow. |
| Collaborative development | The platform combined my application and Prodigy integration with other contributors' components. The available commit history does not establish individual ownership of all later system-wide repairs. |
| My thesis contribution | Architecture analysis, implementation documentation, review of test evidence, workflow evaluation and manuscript preparation. |

## 6. Development work and timeline

### 6.1 My development activities

The timeline covers my application and Prodigy integration work. All periods are in 2026 and are approximate month ranges, not exact completion dates. February–April has Git evidence; later periods are reconstructed from the reported contribution and logical task order.

| Activity | Approximate period | Work and outcome |
| --- | --- | --- |
| Interface and translations | February | Adjusted interface elements and added English/Russian labels. |
| React SPA | February–March | Created the React/TypeScript application structure, routes and page navigation. |
| Dataset and model pages | March–April | Built lists, detail pages and forms for dataset and model management. |
| Django REST API | March–April | Added API endpoints connecting user actions to existing Django operations. |
| React and API integration | April–May | Connected forms and actions to the API; displayed background-task status. |
| Prodigy integration | May–June | Integrated Prodigy into the project and connected annotation access to the web application. |
| Annotation workflow | June–July | Connected dataset selection and annotation controls to the existing labelling workflow. |
| Training and prediction | July–August | Refined web controls and status feedback for training, serving and prediction. |
| Workflow checks | August–September | Checked the annotation-to-prediction flow and reviewed interface status/error feedback. |
| Technical documentation | September–October | Documented application and Prodigy integration; reviewed existing test logs and results. |

### 6.2 Gantt chart for my development work

Legend: C = completed development activity; I = ongoing documentation or evidence review; blank = no activity assigned. Historical month ranges are estimates.

| Activity | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Interface and translations | C |  |  |  |  |  |  |  |  |
| React SPA | C | C |  |  |  |  |  |  |  |
| Dataset and model pages |  | C | C |  |  |  |  |  |  |
| Django REST API |  | C | C |  |  |  |  |  |  |
| React and API integration |  |  | C | C |  |  |  |  |  |
| Prodigy integration |  |  |  | C | C |  |  |  |  |
| Annotation workflow |  |  |  |  | C | C |  |  |  |
| Training and prediction |  |  |  |  |  | C | C |  |  |
| Workflow checks |  |  |  |  |  |  | C | C |  |
| Technical documentation |  |  |  |  |  |  |  | C | I |

## 7 Results

The thesis documented the architecture, my implementation contribution, integration and test results, workflow evaluation and limitations. All tests in the recorded final suites passed. The results demonstrated the tested integration without establishing production readiness, scalability or a target classification accuracy.

## 8 References

1. Kreuzberger, D., Kühl, N. and Hirschl, S. (2022). Machine Learning Operations (MLOps): Overview, Definition, and Architecture. [arXiv:2205.02302](https://arxiv.org/abs/2205.02302).

2. Sculley, D. et al. (2015). Hidden Technical Debt in Machine Learning Systems. [Advances in Neural Information Processing Systems 28](https://proceedings.neurips.cc/paper/2015/hash/86df7dcfd896fcaf2674f757a2463eba-Abstract.html).

3. Devlin, J., Chang, M.-W., Lee, K. and Toutanova, K. (2019). BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding. [NAACL-HLT, pp. 4171–4186](https://aclanthology.org/N19-1423/).

Official documentation: [Kedro](https://docs.kedro.org/en/stable/), [Kubernetes](https://kubernetes.io/docs/concepts/), [Prodigy text classification](https://prodi.gy/docs/text-classification), [Django 6.0](https://docs.djangoproject.com/en/6.0/), [Django REST framework](https://www.django-rest-framework.org/), [React](https://react.dev/learn), [Hugging Face text classification](https://huggingface.co/docs/transformers/tasks/sequence_classification), [FastAPI](https://fastapi.tiangolo.com/) and [PostgreSQL 18](https://www.postgresql.org/docs/18/). Accessed 1 October 2026.

Project evidence: the Project Overview, project plan, Git history, source code and the 26 September implementation report and test logs. Historical dates and shared-work attribution remain subject to the accompanying checklist.
