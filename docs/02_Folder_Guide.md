# 02 — Folder Guide

Status: V1.0/v1.1 package structure **built and tested** (73 tests, see [10_Roadmap.md](10_Roadmap.md)). **v2.0 additions below are designed, not yet implemented** — marked inline in the tree. Includes the legacy-folder reconciliation resolved 2026-07-14 (see [../learning/architecture_notes.md](../learning/architecture_notes.md)).

## Top-level folders

| Folder | Purpose | What belongs here | What doesn't |
|---|---|---|---|
| `learning/` | Running project journal, split by topic | `python_notes.md`, `git_notes.md`, `architecture_notes.md`, `playwright_notes.md`, `database_notes.md`, indexed from `Project Learning.md` | Formal architecture docs (`docs/`), raw platform research (`notes/`) |
| `docs/` | Project documentation — the numbered files in this folder | Architecture, data model, roadmap, glossary, journal | Code, prompts, raw data |
| `notes/` | Raw research on rental platforms and the rental market | Site structure/auth/rate-limit findings, market observations | Curated lessons (`learning/`), formal docs (`docs/`) |
| `prompts/` | Prompt templates used by the agent at runtime | Versioned `.txt`/`.md` prompt files referenced from `src/` | One-off exploratory prompts |
| `src/` | Source code — see package structure below | Application code | Notes, data, generated output |
| `data/` | Persistent data | `rental_intelligence.db` (the database — see [03_Data_Model.md](03_Data_Model.md)), plus file-based stores below | Anything the agent generates as a *deliverable* (that's `output/`) |
| `output/` | Generated deliverables | HTML reports produced by a run | Anything checked in as a fixed input |
| `images/` | Doc-support image assets | Screenshots/diagrams referenced *from docs* | Listing photos (those go in `data/media/`) |
| `tests/` | Test suite | Mirrors `src/` structure 1:1 | — |

## `data/` subfolders

Revised now that SQLite is the system of record for structured data (see [03_Data_Model.md](03_Data_Model.md)) — `apartments/`, `search_history/`, and `platform_registry/` as originally scaffolded on 2026-07-13 are now superseded by database tables and kept only as legacy/empty unless repurposed:

| Subfolder | Purpose | Status |
|---|---|---|
| `knowledge_base/` | Hand-authored source material later loaded into the `knowledge_entries` table | Active |
| `media/` | Downloaded listing images, referenced by `apartment_images.local_path` | Active |
| `raw_pages/` | Unprocessed HTML/screenshots per fetch, referenced by `raw_captures.raw_page_path` | Active |
| `cache/` | Short-lived, safe-to-delete request cache | Active |
| `platform_registry/`, `apartments/`, `search_history/` | Pre-SQLite scaffolding | Superseded — leave empty, do not write new code against these; revisit deletion once `storage/` is implemented and nothing references them |

## `src/` package structure

```
src/
  core/
    __init__.py
    agent.py                 # RentalResearchAgent — the orchestrator (see 01_System_Architecture.md)
    config.py                # app-wide configuration loading
  search/
    __init__.py
    search_request.py        # SearchRequest — see 04_Search_Request.md
    criteria.py               # v2.0: registry MECHANICS only (FilterDefinition, register(),
                                # get_filter(), apply_filters()) — individual filters move out
                                # to filters/ below [v2.0, designed]
    filters/                    # [v2.0, designed] — see 04_Search_Request.md
      __init__.py                 # imports every category module so registration happens on import
      budget.py                    # min_price, max_price (migrated from criteria.py, unchanged logic)
      property.py                   # min_bedrooms/bathrooms/sqft (migrated) + property_type, room_type
      timing.py                      # move_in_date, min_availability_duration
      proximity.py                    # max_walking_minutes, max_transit_minutes, nearby_* filters
      amenity.py                       # private_bathroom, air_conditioning, balcony, parking, ...
      occupant.py                       # gender, student_only, professionals_only
      score.py                           # safety_score, noise_score, lifestyle/convenience/location_score
  discovery/
    __init__.py
    discovery_agent.py         # DiscoveryAgent — see 05_Platform_Discovery.md
    platform_registry.py         # reads/writes the `platforms` table
    known_platforms.py             # seed candidate list — see 05_Platform_Discovery.md
    automatic/                       # [live, new package, v2.5 Step 13] the Automatic
                                       # Platform Discovery Agent — see 29_Automatic_Platform_Discovery.md
      __init__.py                        # imports providers/ -> self-registration
      exceptions.py                        # DiscoveryException hierarchy
      metadata.py                           # DiscoveryProviderMetadata
      models.py                              # DiscoveryRequest/Run/Policy, PlatformCandidate/Evidence/
                                               # VerificationResult/CapabilityEstimate/Evaluation,
                                               # PlatformStatus (12)/PlatformClassification (13),
                                               # DiscoveryStatistics/Comparison
      base_provider.py                        # DiscoveryProvider (ABC) — metadata()/discover(request)
      registry.py                              # DiscoveryProviderRegistry, register_discovery_provider()
      factory.py                                # DiscoveryProviderFactory — get()/resolve()
      normalization.py                           # normalize_domain/name, duplicate-candidate lookups
      classification.py                           # deterministic keyword-scoring classifier
      verification.py                              # PageFetcher protocol, HttpPageFetcher, domain/content checks
      capability.py                                 # 14-capability heuristic estimator (always is_estimate=True)
      evidence_collection.py                         # one DiscoveredURL + fetch -> the 15 named evidence types
      statistics.py                                   # compute_discovery_statistics(), compare_discovery_runs()
      service.py                                       # thin storage orchestration (mirrors feedback/service.py)
      agent.py                                          # AutomaticDiscoveryAgent — the 12-step pipeline
      report.py                                          # HTML + JSON discovery report generator
      providers/
        __init__.py                                        # eager imports -> self-registration
        curated_seed_provider.py                             # surfaces known_platforms.py entries by country
        manual_url_provider.py                                # surfaces DiscoveryRequest.manual_urls as-is
  connectors/
    __init__.py
    base.py                      # RawListing only — the old Connector ABC was removed in
                                   # v2.0 Step 5, replaced by sdk/base_connector.py
    sdk/                           # [v2.0 Step 5, live — new package] the Connector SDK &
                                    # Plugin Framework — see 18_Connector_SDK.md
      __init__.py                   # public API re-exports (incl. ConnectorHealth, which
                                      # actually lives in src/knowledge/models.py)
      exceptions.py                  # ConnectorException hierarchy
      metadata.py                     # ConnectorMetadata, ConnectorCapabilities
      configuration.py                 # ConnectorConfiguration
      result.py                         # ConnectorResult
      validator.py                       # ConnectorValidator, ValidationResult/Warning
      registry.py                         # ConnectorRegistry, register_connector decorator
      factory.py                           # ConnectorFactory — the only sanctioned way
                                             # to obtain a connector instance
      base_connector.py                      # BaseConnector — the template method
    README.md                     # orientation + link to 06_Connector_Framework.md
    demo_platform.py               # reference/demo connector — rebuilt on BaseConnector [v2.0 Step 5]
    demo_platform_two.py            # second reference connector — rebuilt on BaseConnector [v2.0 Step 5]
    fixtures/
      demo_platform/listings.html, images/
      demo_platform_two/listings.html, images/
    rentcast/                     # [v2.0 Step 7, live — new package] the first production
                                    # (real, non-demo) connector — see 20_First_Production_Connector.md
      __init__.py                   # imports connector.py -> runs @register_connector
      connector.py                   # RentCastConnector(BaseConnector) — platform_id = "rentcast"
      client.py                       # RentCastClient — HTTP transport, retry/backoff, auth header
      fixtures/
        sample_response.json            # hand-built, schema-accurate example (not a live capture)
    sample_json_feed/             # [SDK Validation Sprint, new package] a fourth reference
                                    # connector, JSON not HTML — see 22_SDK_Validation_Sprint.md.
                                    # Deliberately NOT seeded in known_platforms.py — a pure SDK
                                    # conformance/validation vehicle, not a real data source.
      __init__.py
      connector.py                   # SampleJsonFeedConnector(BaseConnector) — overrides _collect()
      fixtures/
        feed.json, images/
  collectors/
    __init__.py
    browser_collector.py           # Playwright-based fetch
    http_collector.py               # plain HTTP fetch, for platforms with a usable API
    image_collector.py               # downloads listing images into data/media/
    raw_page_store.py                 # persists raw HTML/screenshots into data/raw_pages/
  analyzers/
    __init__.py
    normalizer.py                     # RawListing -> Apartment shape; v2.0: also normalizes `description`
    deduplicator.py                    # within-platform duplicate detection (V1); cross-platform is V2
    enricher.py                         # price_per_sqft (computed-on-read) — unchanged by v2.0
    change_detector.py                   # price/status comparison only — unchanged by v2.0 Step 2;
                                           # title/description/images comparison lives in history/ instead
                                            # (see history_service.py below and learning/architecture_notes.md)
    engine.py                             # composes the pipeline's write sequence; v2.0 Step 2: also
                                            # calls the Apartment History Engine + Image Change Detection
    distance.py                             # [v2.0, designed] walking/transit distance — see 07_Analysis_Engine.md
    nearby.py                                # [v2.0, designed] nearby-amenity counts/distances
    scores.py                                 # [v2.0, designed] lifestyle/convenience/location scores
  history/                                        # [v2.0 Step 2, live — new package] the Apartment History Engine
    __init__.py
    models.py                                       # Change / ChangeType — the structured comparison result
    comparison.py                                    # pure per-field comparison functions -> Change objects
    history_service.py                                # write (record_new_apartment/record_reobservation) +
                                                         # read (latest/previous version, timelines) — no DB
                                                         # state of its own beyond the `conn` each call takes
  search_memory/                                  # [v2.0 Step 3, live — new package] Search Memory & Comparison Engine
    __init__.py
    models.py                                       # SearchExecution/SearchComparison/SearchStatistics/
                                                       # SearchTimeline + the small Apartment*Change dataclasses
    comparison.py                                    # pure: diff_apartment_sets, platform_coverage_change,
                                                       # search_quality
    search_memory_service.py                          # write (record_completed_search) + read (latest_search/
                                                         # search_history/search_timeline/compare_searches/
                                                         # average_execution_time/average_apartment_count/
                                                         # search_statistics)
  knowledge/                                    # [v2.0 Step 4, live — new package] the Knowledge Engine,
                                                   # see 16_Knowledge_Engine.md. Named `knowledge_service.py`
                                                   # rather than the originally-sketched `engine.py`, for
                                                   # naming consistency with history_service.py/search_memory_service.py
    __init__.py
    models.py                                     # PlatformKnowledge/ConnectorHealth/CityKnowledge/
                                                     # KnowledgeSummary
    metrics.py                                      # pure: extraction/image/availability_quality_score,
                                                       # duplicate_rate, ranking_usefulness_score
    knowledge_service.py                              # write (record_platform_observation, recomputes
                                                         # Platform Intelligence rollups) + read
                                                         # (best_platforms/platform_reliability/
                                                         # connector_health/average_city_price/
                                                         # knowledge_summary/platform_statistics/
                                                         # city_statistics)
  analysis/                                       # [v2.0 Step 6, live — new package] the Deep Analysis Engine,
                                                     # see 19_Analysis_Engine.md
    __init__.py
    models.py                                       # AnalysisContext/AnalyzerMetadata/AnalyzerResult/
                                                       # CompositeScore/AnalysisResult
    base_analyzer.py                                  # BaseAnalyzer — thin contract, not a template method
    registry.py                                         # AnalysisRegistry, register_analyzer decorator
    geo.py                                               # pure haversine_km — the only real "location math"
    scoring.py                                            # CompositeScoreDefinition/ScoringConfiguration/
                                                            # compute_composite_scores/default_scoring_configuration
    pipeline.py                                             # AnalysisPipeline — every analyzer, one apartment
    engine.py                                                # AnalysisEngine — every apartment, one search
                                                               # (what core/agent.py holds)
    analysis_service.py                                        # record_analysis / latest_analysis / analysis_history
    analyzers/
      __init__.py                                                # imports every analyzer -> self-registration
      walking_distance.py
      public_transport.py
      nearby_amenity.py                                            # shared base + all 9 "nearby X" analyzers
  ranking/
    __init__.py
    ranking_engine.py                     # see 08_Ranking_System.md
    scoring.py                             # weighted-sum scoring functions
  storage/
    __init__.py
    database.py                             # SQLite connection/session management
    schema.sql                               # DDL for all tables in 03_Data_Model.md
    models.py                                 # dataclasses mirroring each table
    apartment_repository.py                   # CRUD + price/availability history + images for apartments;
                                                # v2.0 Step 2: also update_apartment_details,
                                                # mark_image_not_current
    apartment_history_repository.py             # [v2.0 Step 2, live] apartment_change_log,
                                                  # apartment_image_events — data access only
    search_repository.py                       # search_requests / search_results; also exposes
                                                 # row_to_search_request(), shared with the module below
    search_memory_repository.py                  # [v2.0 Step 3, live] search_observed_apartments,
                                                    # complete_search_execution (the run-stats UPDATE),
                                                    # find_previous_search, get_search_history
    reference_data_repository.py                 # knowledge_entries — curated reference facts, unrelated
                                                    # to src/knowledge/ (renamed from knowledge_repository.py
                                                    # in v2.0 Step 4.5 to stop the two "knowledge"s colliding)
    platform_intelligence_repository.py            # [v2.0 Step 4, live] platform_performance_observations —
                                                     # data access only; rollup writes are
                                                     # discovery/platform_registry.py::update_platform_rollups
                                                     # (platforms is that module's table, not storage/'s)
    analysis_metrics_repository.py                   # [v2.0 Step 6, live] apartment_analysis_metrics —
                                                       # data access only; this IS "AnalysisRepository"
                                                       # from the mission, see 19_Analysis_Engine.md
    discovery_repository.py                            # [live, v2.5 Step 13] discovery_runs, platform_candidates,
                                                         # platform_evidence, platform_verification_observations,
                                                         # platform_capability_estimates, platform_duplicate_links,
                                                         # discovery_provider_observations — data access only;
                                                         # every table but platform_candidates/discovery_runs is
                                                         # strictly append-only (no update/delete function exists)
    monitoring_repository.py                           # [live, v2.5 Step 14] saved_searches, saved_search_versions,
                                                         # monitoring_schedules, monitoring_runs, monitoring_events,
                                                         # event_acknowledgements, monitoring_statistics,
                                                         # report_artifacts — data access only; saved_searches/
                                                         # monitoring_schedules/monitoring_runs/monitoring_events
                                                         # each have exactly one mutation function, every other
                                                         # table is strictly append-only
    notification_repository.py                          # [live, v2.5 Step 15] notification_preferences/_versions,
                                                          # notification_templates, notification_batches/_deliveries/
                                                          # _delivery_events/_digests/_attempts/_messages,
                                                          # rate_limit_observations, channel_health_observations,
                                                          # notification_acknowledgements — data access only;
                                                          # preferences/batches/deliveries are current-state (one
                                                          # mutation function each), every other table is strictly
                                                          # append-only
  services/
    __init__.py
    report_generator.py                           # HTML Report Generator — see 09_Report_System.md
  ui/
    __init__.py
    cli.py                                          # entry point — the only place a human interacts with the system
    feedback_cli.py                                    # [live, v2.5 Step 12] record/profile/explain/history/undo/reset/export
    discovery_cli.py                                    # [live, v2.5 Step 13] discover/list-*/compare-runs/
                                                          # approve-candidate/reject-candidate/view-evidence/view-coverage-summary
    monitoring_cli.py                                    # [live, v2.5 Step 14] create/list/view/update/enable/disable
                                                          # -saved-search, run-now/run-due, list-runs/compare-runs,
                                                          # list-events/acknowledge-event/export-events, next-run,
                                                          # health, task-scheduler-examples
    notification_cli.py                                    # [live, v2.5 Step 15] create/list/view/update/enable/
                                                            # disable-preference, preview, send-test-notification,
                                                            # deliver-pending, generate-digest, retry-due,
                                                            # list-deliveries/list-failed-deliveries/retry-delivery/
                                                            # cancel-delivery, acknowledge-notification,
                                                            # channel-health, statistics, export-history,
                                                            # task-scheduler-examples
  utils/
    __init__.py
    logging.py                                        # [v2.0 Step 7, live] get_logger()/StructuredFormatter —
                                                         # first real use is rentcast/'s retry/pagination logging
    ids.py                                            # UUID generation for apartments/search_requests
  providers/                                            # [live] Production Provider Framework — see
                                                          # 21_Provider_Abstraction_Layer.md + 24_Production_Providers.md
    __init__.py                                            # imports data/ and ai/ -> self-registration
    base.py                                                  # Provider (ABC), ProviderKind (DATA/AI)
    scoring.py                                                # ProviderMetadata/ScoringWeights/ProviderScore/
                                                                 # score_provider()
    registry.py                                                 # ProviderRegistry, register_provider()
    router.py                                                    # ProviderRouter, ProviderRunOutcome/ProviderAttempt
    exceptions.py                                                 # +ProviderValidationError [v2.5 Step 8]
    configuration.py                                               # ProviderConfiguration [v2.5 Step 8]
    factory.py                                                      # ProviderFactory [v2.5 Step 8]
    health.py                                                        # ProviderHealth, check_provider_health() [v2.5 Step 8]
    metrics.py                                                        # ProviderMetrics, build_/record_provider_metrics()
                                                                        # [v2.5 Step 8]
    statistics.py                                                      # ProviderStatistics, provider_statistics()
                                                                         # [v2.5 Step 8]
    validator.py                                                        # ProviderValidator, ProviderValidationResult
                                                                          # [v2.5 Step 8]
    data/
      __init__.py
      base_data_provider.py                                        # DataProvider(Provider) — platform_id, search()
      rentcast_data_provider.py                                      # wraps RentCastConnector (v2.0 Step 7)
      local_demo_data_provider.py                                      # wraps DemoPlatformConnector (v2.0 Step 5)
    ai/
      __init__.py
      base_ai_provider.py                                            # AIProvider(Provider) — summarize()
      ollama_ai_provider.py                                            # real HTTP to a local Ollama server
      null_ai_provider.py                                                # always available, honest None summary
  filter_engine/                                        # [live, new package] the Dynamic Filter Engine —
                                                          # see 25_Dynamic_Filter_Engine.md
    __init__.py                                            # imports filters/ -> self-registration
    base_filter.py                                            # BaseFilter (ABC), FilterContext
    metadata.py                                                # FilterMetadata
    configuration.py                                            # FilterConfiguration
    result.py                                                    # FilterResult
    registry.py                                                   # FilterRegistry, register_filter()
    factory.py                                                     # FilterFactory
    composition.py                                                  # FilterCondition/FilterGroup/FilterOperator, evaluate()
    validator.py                                                     # FilterValidator
    statistics.py                                                     # FilterStatistics, compute_filter_statistics()
    history.py                                                         # FilterHistoryEntry, record/get_filter_execution
    sync.py                                                             # sync_filter_definitions()
    engine.py                                                            # FilterEngine — the pipeline itself
    exceptions.py                                                         # FilterException hierarchy
    filters/
      __init__.py                                                          # eager imports -> self-registration
      core_filters.py                                                        # 9 data-backed filters
      distance_filters.py                                                      # 3 analysis-metric-backed filters
      dormant_base.py                                                           # shared bases for dormant filters
      amenities.py                                                                # 14 dormant amenity filters
      preferences_and_other.py                                                     # 13 more dormant filters
  geography/                                            # [live, new package] the Geographic Intelligence Engine —
                                                          # see 26_Geographic_Intelligence.md
    __init__.py                                            # imports providers/ -> self-registration
    base_provider.py                                          # GeoProvider (ABC), GeoContext
    metadata.py                                                # GeoProviderMetadata
    models.py                                                   # TravelMode, GeoResult, NearbyPlace, GeoEnrichment
    registry.py                                                  # GeoProviderRegistry, register_geo_provider()
    factory.py                                                    # GeoProviderFactory
    cache.py                                                       # GeoCache — TTL key/value store
    calculators.py                                                  # DistanceCalculator/TravelTimeCalculator/RouteCalculator
    nearby_search.py                                                 # NearbySearch, NEARBY_CATEGORIES (17)
    engine.py                                                         # GeographicEngine — the orchestrator itself
    statistics.py                                                      # GeoStatistics, compute_geo_statistics()
    history.py                                                          # GeoHistoryEntry, record/get_geo_history
    exceptions.py                                                        # GeoException hierarchy
    providers/
      __init__.py                                                          # eager imports -> self-registration
      haversine_provider.py                                                  # real distance + estimated travel time + curated nearby
  ranking_v2/                                           # [live, new package] the Intelligent Ranking Engine V2 —
                                                          # see 27_Intelligent_Ranking_Engine.md
    __init__.py                                            # imports rules/ -> self-registration
    base_rule.py                                              # RankingRule (ABC), RankingContext
    metadata.py                                                # RankingRuleMetadata
    models.py                                                   # RankingEvidence, RuleContribution, RankingConfidence,
                                                                 # RankingExplanation, RankedApartmentV2
    registry.py                                                  # RankingRuleRegistry, register_ranking_rule()
    weights.py                                                    # RankingWeights
    profile.py                                                     # RankingProfile, DEFAULT_PROFILE, COMPREHENSIVE_PROFILE
    pipeline.py                                                     # RankingPipeline — renormalization + explanation
    engine.py                                                        # RankingEngineV2 — the outward-facing entry point
    statistics.py                                                     # RankingStatistics, compute_ranking_statistics()
    exceptions.py                                                      # RankingException hierarchy
    rules/
      __init__.py                                                        # eager imports -> self-registration
      _phrasing.py                                                         # shared qualitative-detail phrase helper
      price_rules.py                                                        # price, price_trend
      geo_rules.py                                                           # walking_distance, public_transport, lifestyle
      availability_rules.py                                                   # availability
      reliability_rules.py                                                     # platform_reliability, connector_reliability
      context_rules.py                                                          # filter_preferences, analysis_composite,
                                                                                 # provider_health, search_history
  feedback/                                             # [live, new package] the User Feedback and Preference
                                                          # Learning Engine — see 28_User_Feedback_and_Preference_Learning.md
    __init__.py                                            # imports rules/ -> self-registration
    base_rule.py                                              # PreferenceRule (ABC) + 4 shared aggregate() bases, PreferenceContext
    metadata.py                                                # PreferenceRuleMetadata
    models.py                                                   # FeedbackEvent, FeedbackMode, PreferenceObservation/Evidence/
                                                                 # Adjustment/Confidence/Value/Profile/Summary, FeedbackStatistics
    event_types.py                                               # FeedbackEventType constants (open-ended, not an enum)
    decay.py                                                      # DecayConfig, compute_confidence(), decayed_weight()
    registry.py                                                    # FeedbackRegistry, register_preference_rule()
    engine.py                                                       # FeedbackEngine — record/build/explain/undo/reset/export/compare
    service.py                                                       # FeedbackService — thin storage orchestration
    ranking_adapter.py                                                # suggest/resolve RankingProfile from a PreferenceProfile
    filter_integration.py                                              # records repeated filter choices as feedback
    exceptions.py                                                       # FeedbackException hierarchy
    rules/
      __init__.py                                                        # eager imports -> self-registration
      price_rules.py                                                       # price_sensitivity, maximum_budget
      listing_rules.py                                                      # availability_importance, property_type, minimum_area,
                                                                             # number_of_rooms, platform
      geo_rules.py                                                           # walking_distance, public_transport, lifestyle,
                                                                              # nearby_services, neighborhood
      amenity_rules.py                                                       # 11 dormant-field dimensions (filter-choice-only evidence)
  monitoring/                                           # [live, new package, v2.5 Step 14] the Continuous
                                                          # Monitoring & Saved Search Engine — see 30_Continuous_Monitoring.md
    __init__.py                                            # imports detectors/ -> self-registration
    exceptions.py                                            # MonitoringException hierarchy
    metadata.py                                               # EventDetectorMetadata
    models.py                                                  # SavedSearch/Version, MonitoringSchedule/Run/RunStatus/
                                                                 # Policy/Configuration/Event/EventType/Comparison/
                                                                 # RankChange/Statistics/Report/Health
    base_detector.py                                            # EventDetector (ABC), MonitoringDetectionContext
    registry.py                                                  # MonitoringRegistry, register_event_detector()
    service.py                                                    # thin storage orchestration (mirrors discovery/automatic/service.py)
    scheduling.py                                                  # due_saved_searches/next_run_time/claim_due_run/
                                                                     # release_run_claim/mark_run_*/compute_health/
                                                                     # task_scheduler_command_examples
    significance.py                                                 # deterministic significance scoring, no ML
    deduplication.py                                                 # make_dedup_key(), is_duplicate() — checked
                                                                       # centrally, once, by the engine
    removal.py                                                        # missing -> possibly_removed -> confirmed_removed
    statistics.py                                                      # compute_statistics(), compare_monitoring_runs()
    feedback_integration.py                                             # record_user_reaction() — never called automatically
    engine.py                                                            # MonitoringEngine — saved-search lifecycle + 12-step workflow
    report.py                                                            # full + change-only HTML/JSON monitoring reports
    detectors/
      __init__.py                                                        # eager imports -> self-registration
      apartment_change_detector.py                                         # new match/listing, price, availability,
                                                                             # listing_updated/images/description,
                                                                             # removal threshold, returned
      ranking_change_detector.py                                            # rank_increased/decreased, better_match_found
      filter_match_detector.py                                               # filter_match_gained/lost
      platform_health_detector.py                                             # connector_failure/recovered
      discovery_detector.py                                                    # discovery_found_new_platform,
                                                                                 # platform_became_accessible
  notifications/                                        # [live, new package, v2.5 Step 15] the Notification
                                                          # Delivery Engine — see 31_Notification_Delivery.md
    __init__.py                                            # imports channels/ and templates/ -> self-registration
    exceptions.py                                            # NotificationException hierarchy
    metadata.py                                               # NotificationChannelMetadata
    models.py                                                  # NotificationPreference/Version, ChannelResult, Message,
                                                                 # Attempt, Digest, Batch, Delivery/DeliveryStatus,
                                                                 # Eligibility, Statistics, Health, Policy, Configuration
    base_channel.py                                             # NotificationChannel (ABC) — configure/validate_
                                                                  # configuration/supports/health_check/preview/send/
                                                                  # send_batch/serialize_result/channel_info
    registry.py                                                  # NotificationChannelRegistry, register_notification_channel()
    factory.py                                                    # NotificationChannelFactory
    base_template.py                                               # NotificationTemplate (ABC), TemplateContext, RenderedTemplate
    template_registry.py                                            # NotificationTemplateRegistry, register_notification_template()
    service.py                                                       # thin storage orchestration (mirrors monitoring/service.py)
    eligibility.py                                                    # evaluate_event()/explain_eligibility() — content-based only
    quiet_hours.py                                                     # is_in_quiet_hours()/next_permitted_time() — timezone-aware
    rate_limiting.py                                                    # is_rate_limited()/record_send()
    retry.py                                                             # is_retryable()/should_dead_letter()/compute_next_attempt_at()
    scheduling.py                                                         # next_digest_time/is_digest_due/next_delivery_time/
                                                                            # task_scheduler_command_examples
    statistics.py                                                          # compute_statistics()
    feedback_integration.py                                                 # record_user_reaction() — never called automatically
    engine.py                                                                # NotificationEngine — preference lifecycle + delivery workflow
    channels/
      __init__.py                                                            # eager imports -> self-registration
      console_channel.py                                                       # ConsoleNotificationChannel — always enabled
      file_channel.py                                                          # FileNotificationChannel — always enabled, never overwrites
      email_channel.py                                                         # EmailNotificationChannel — SMTP, disabled until configured
      webhook_channel.py                                                       # WebhookNotificationChannel — HTTP POST, disabled until configured
    templates/
      __init__.py                                                            # eager imports -> self-registration
      helpers.py                                                              # apartment_for_event/apartment_image_paths/report_links_for_run
      event_alert_templates.py                                                # 6 immediate alert templates, one shared base
      digest_templates.py                                                     # daily_digest/weekly_digest, one shared base
  rental_agent.py                                       # thin script wrapper: parses argv, calls ui.cli
```

## Legacy folder reconciliation (resolves the item deferred on 2026-07-13)

| Legacy path | Disposition | Reason |
|---|---|---|
| Legacy path | Disposition | Status |
|---|---|---|
| `src/browser/browser_manager.py` | Moved into `src/collectors/browser_collector.py`, expanded from a one-off test function into a reusable `BrowserCollector` context-manager class | **Done** (2026-07-14) |
| `config/settings.json`, `src/config/config_loader.py`, `src/model/apartment.py`, `src/models/configuration.py` | Deleted, not migrated — confirmed stale/experimental by the user (2026-07-14): modeled a different, narrower concept (flatshare room search in Valencia via specific platforms) that doesn't reflect the confirmed V1.0 design. `src/storage/models.py` defines a fresh `Apartment` dataclass from [03_Data_Model.md](03_Data_Model.md) instead; `src/core/config.py` is a fresh, minimal app-config module (paths + `.env` loading), not a revival of the old per-search `Configuration` schema. See [../learning/architecture_notes.md](../learning/architecture_notes.md). | **Done** (2026-07-14) |
| `main.py` (project root) | Deleted — only ever exercised the deleted `config_loader`/prototype code, and wasn't part of the documented structure (the real V1 entry point is `src/rental_agent.py`, see below) | **Done** (2026-07-14) |
| `src/data_source/`, `src/filters/`, `src/exporters/`, `src/reports/`, `src/maps/` | Deleted (all were empty) — superseded by `connectors/`+`collectors/`, `search/criteria.py`, `services/report_generator.py`, and `analyzers/enricher.py` respectively | **Done** (2026-07-14) |
| `src/ai/` | Kept, empty, reserved | Not part of V1.0 scope (confirmed 2026-07-14, see Non-Goals in [00_Project_Vision.md](00_Project_Vision.md)) — reserved for V2 AI-assisted ranking explanations/report summaries |

This table is a historical record of the reconciliation now that it's done — see [../learning/architecture_notes.md](../learning/architecture_notes.md) for the full reasoning behind each disposition.

## Root files

| File | Purpose |
|---|---|
| `README.md` | Quick orientation + setup instructions for a new clone |
| `CLAUDE.md` | Working agreement for how Claude should operate in this project |
| `requirements.txt` | Python dependencies |
| `.env` | Local secrets/config (gitignored, never committed) |
| `.gitignore` | Excludes `.env`, `.venv/`, `__pycache__/`, generated `output/` contents |

## Related Documents

- [01_System_Architecture.md](01_System_Architecture.md)
- [15_Agent_Architecture.md](15_Agent_Architecture.md), [16_Knowledge_Engine.md](16_Knowledge_Engine.md), [17_Search_Memory.md](17_Search_Memory.md) — v2.0 additions
