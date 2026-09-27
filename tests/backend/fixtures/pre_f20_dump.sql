--
-- PostgreSQL database dump
--

-- Dumped from database version 17.2
-- Dumped by pg_dump version 17.2

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: acquisition; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA acquisition;


--
-- Name: company_radar; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA company_radar;


--
-- Name: crm; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA crm;


--
-- Name: matching; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA matching;


--
-- Name: opportunities; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA opportunities;


--
-- Name: platform; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA platform;


--
-- Name: profile; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA profile;


--
-- Name: unaccent; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA public;


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: prevent_stage_history_mutation(); Type: FUNCTION; Schema: crm; Owner: -
--

CREATE FUNCTION crm.prevent_stage_history_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            RAISE EXCEPTION 'stage history is immutable';
        END;
        $$;


--
-- Name: prevent_match_analysis_mutation(); Type: FUNCTION; Schema: matching; Owner: -
--

CREATE FUNCTION matching.prevent_match_analysis_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            RAISE EXCEPTION 'match analyses are immutable';
        END;
        $$;


--
-- Name: prevent_match_assessment_mutation(); Type: FUNCTION; Schema: matching; Owner: -
--

CREATE FUNCTION matching.prevent_match_assessment_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            RAISE EXCEPTION 'match assessments are immutable';
        END;
        $$;


--
-- Name: prevent_match_factor_mutation(); Type: FUNCTION; Schema: matching; Owner: -
--

CREATE FUNCTION matching.prevent_match_factor_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
        BEGIN
            RAISE EXCEPTION 'match factors are immutable';
        END;
        $$;


--
-- Name: f_unaccent(text); Type: FUNCTION; Schema: opportunities; Owner: -
--

CREATE FUNCTION opportunities.f_unaccent(text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    AS $_$
            SELECT public.unaccent('public.unaccent', $1)
        $_$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: payload_retention_event; Type: TABLE; Schema: acquisition; Owner: -
--

CREATE TABLE acquisition.payload_retention_event (
    id uuid NOT NULL,
    raw_item_id uuid NOT NULL,
    expired_at timestamp with time zone DEFAULT now() NOT NULL,
    retention_policy_version character varying(32) NOT NULL,
    retention_days integer NOT NULL,
    payload_hash character varying(64) NOT NULL,
    source_definition_id uuid NOT NULL
);


--
-- Name: raw_item; Type: TABLE; Schema: acquisition; Owner: -
--

CREATE TABLE acquisition.raw_item (
    id uuid NOT NULL,
    source_run_id uuid NOT NULL,
    source_definition_id uuid NOT NULL,
    external_id character varying(512),
    canonical_url character varying(2048),
    identity_key character varying(2048) NOT NULL,
    payload_hash character varying(64) NOT NULL,
    content_type character varying(255),
    fetched_at timestamp with time zone DEFAULT now() NOT NULL,
    parser_version character varying(128),
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: raw_item_payload; Type: TABLE; Schema: acquisition; Owner: -
--

CREATE TABLE acquisition.raw_item_payload (
    raw_item_id uuid NOT NULL,
    payload jsonb,
    stored_at timestamp with time zone DEFAULT now() NOT NULL,
    expired_at timestamp with time zone,
    retention_policy_version character varying(32),
    CONSTRAINT ck_raw_item_payload_expiry CHECK ((((payload IS NOT NULL) AND (expired_at IS NULL)) OR ((payload IS NULL) AND (expired_at IS NOT NULL))))
);


--
-- Name: source_alert_incident; Type: TABLE; Schema: acquisition; Owner: -
--

CREATE TABLE acquisition.source_alert_incident (
    id uuid NOT NULL,
    source_definition_id uuid NOT NULL,
    opened_at timestamp with time zone DEFAULT now() NOT NULL,
    opened_by_run_id uuid,
    consecutive_failures integer NOT NULL,
    error_code character varying(64),
    error_summary text,
    alert_sent_at timestamp with time zone,
    alert_delivery character varying(16) DEFAULT 'PENDING'::character varying NOT NULL,
    recovered_at timestamp with time zone,
    recovered_by_run_id uuid,
    recovery_sent_at timestamp with time zone,
    recovery_delivery character varying(16),
    correlation_id character varying(255),
    CONSTRAINT ck_source_alert_incident_delivery CHECK (((alert_delivery)::text = ANY ((ARRAY['PENDING'::character varying, 'WEBHOOK'::character varying, 'LOG_ONLY'::character varying, 'FAILED'::character varying])::text[]))),
    CONSTRAINT ck_source_alert_incident_failures CHECK ((consecutive_failures > 0)),
    CONSTRAINT ck_source_alert_incident_recovery_delivery CHECK (((recovery_delivery IS NULL) OR ((recovery_delivery)::text = ANY ((ARRAY['WEBHOOK'::character varying, 'LOG_ONLY'::character varying, 'FAILED'::character varying])::text[]))))
);


--
-- Name: source_checkpoint; Type: TABLE; Schema: acquisition; Owner: -
--

CREATE TABLE acquisition.source_checkpoint (
    source_definition_id uuid NOT NULL,
    checkpoint_type character varying(32) DEFAULT 'cursor'::character varying NOT NULL,
    cursor text,
    updated_since timestamp with time zone,
    etag text,
    last_modified text,
    promoted_by_run_id uuid,
    promoted_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: source_definition; Type: TABLE; Schema: acquisition; Owner: -
--

CREATE TABLE acquisition.source_definition (
    id uuid NOT NULL,
    company_source_id uuid,
    source_type character varying(64) NOT NULL,
    name character varying(255) NOT NULL,
    enabled boolean DEFAULT false NOT NULL,
    schedule character varying(255),
    priority integer DEFAULT 100 NOT NULL,
    rate_limit_policy jsonb DEFAULT '{}'::jsonb NOT NULL,
    configuration jsonb DEFAULT '{}'::jsonb NOT NULL,
    evidence_status character varying(32) DEFAULT 'unverified'::character varying NOT NULL,
    reviewed_at timestamp with time zone,
    terms_reviewed boolean DEFAULT false NOT NULL,
    collector_local_tested boolean DEFAULT false NOT NULL,
    last_health_status character varying(32),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    last_http_attempt_at timestamp with time zone,
    CONSTRAINT ck_source_definition_evidence_status CHECK (((evidence_status)::text = ANY ((ARRAY['unverified'::character varying, 'confirmed'::character varying, 'ats_identified'::character varying, 'careers_page'::character varying, 'dynamic_review'::character varying, 'redirect_review'::character varying, 'access_pending'::character varying])::text[]))),
    CONSTRAINT ck_source_definition_priority CHECK ((priority >= 0))
);


--
-- Name: source_probe; Type: TABLE; Schema: acquisition; Owner: -
--

CREATE TABLE acquisition.source_probe (
    id uuid NOT NULL,
    source_definition_id uuid NOT NULL,
    requested_by character varying(20) NOT NULL,
    status character varying(20) NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    items_seen integer DEFAULT 0 NOT NULL,
    http_requests integer DEFAULT 0 NOT NULL,
    error_code character varying(64),
    detail text,
    evidence_recorded boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_source_probe_requested_by CHECK (((requested_by)::text = ANY ((ARRAY['interface'::character varying, 'script'::character varying])::text[]))),
    CONSTRAINT ck_source_probe_status CHECK (((status)::text = ANY ((ARRAY['RUNNING'::character varying, 'PASSED'::character varying, 'FAILED'::character varying])::text[])))
);


--
-- Name: source_run; Type: TABLE; Schema: acquisition; Owner: -
--

CREATE TABLE acquisition.source_run (
    id uuid NOT NULL,
    source_definition_id uuid NOT NULL,
    status character varying(16) NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    items_seen integer DEFAULT 0 NOT NULL,
    items_persisted integer DEFAULT 0 NOT NULL,
    items_skipped integer DEFAULT 0 NOT NULL,
    items_invalid integer DEFAULT 0 NOT NULL,
    http_requests integer DEFAULT 0 NOT NULL,
    retry_count integer DEFAULT 0 NOT NULL,
    error_code character varying(64),
    error_summary text,
    checkpoint_before text,
    checkpoint_after text,
    correlation_id character varying(255),
    rate_limit_events integer DEFAULT 0 NOT NULL,
    execution_trigger character varying(16) DEFAULT 'ON_DEMAND'::character varying NOT NULL,
    items_announced integer,
    complete boolean DEFAULT false NOT NULL,
    CONSTRAINT ck_source_run_counters CHECK (((items_seen >= 0) AND (items_persisted >= 0) AND (items_skipped >= 0) AND (items_invalid >= 0) AND (http_requests >= 0) AND (retry_count >= 0) AND (rate_limit_events >= 0))),
    CONSTRAINT ck_source_run_execution_trigger CHECK (((execution_trigger)::text = ANY ((ARRAY['ON_DEMAND'::character varying, 'SCHEDULED'::character varying])::text[]))),
    CONSTRAINT ck_source_run_status CHECK (((status)::text = ANY ((ARRAY['PENDING'::character varying, 'RUNNING'::character varying, 'SUCCEEDED'::character varying, 'PARTIAL'::character varying, 'FAILED'::character varying, 'CANCELLED'::character varying])::text[])))
);


--
-- Name: company; Type: TABLE; Schema: company_radar; Owner: -
--

CREATE TABLE company_radar.company (
    id uuid NOT NULL,
    canonical_name character varying(255) NOT NULL,
    normalized_name character varying(255) NOT NULL,
    domain character varying(253),
    priority character varying(20) DEFAULT 'normal'::character varying NOT NULL,
    radar_status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    verification_state character varying(30) DEFAULT 'unverified'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    version integer DEFAULT 1 NOT NULL
);


--
-- Name: company_alias; Type: TABLE; Schema: company_radar; Owner: -
--

CREATE TABLE company_radar.company_alias (
    id uuid NOT NULL,
    company_id uuid NOT NULL,
    alias character varying(255) NOT NULL,
    normalized_alias character varying(255) NOT NULL
);


--
-- Name: company_import_batch; Type: TABLE; Schema: company_radar; Owner: -
--

CREATE TABLE company_radar.company_import_batch (
    id uuid NOT NULL,
    file_hash character varying(64) NOT NULL,
    source_filename character varying(255) NOT NULL,
    status character varying(30) DEFAULT 'running'::character varying NOT NULL,
    report jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone
);


--
-- Name: company_import_issue; Type: TABLE; Schema: company_radar; Owner: -
--

CREATE TABLE company_radar.company_import_issue (
    id uuid NOT NULL,
    batch_id uuid NOT NULL,
    row_number integer NOT NULL,
    code character varying(50) NOT NULL,
    message text NOT NULL,
    raw_data jsonb
);


--
-- Name: company_source; Type: TABLE; Schema: company_radar; Owner: -
--

CREATE TABLE company_radar.company_source (
    id uuid NOT NULL,
    company_id uuid NOT NULL,
    source_type character varying(50) NOT NULL,
    endpoint text NOT NULL,
    external_key character varying(255),
    verification_status character varying(30) DEFAULT 'unverified'::character varying NOT NULL,
    confidence numeric(4,3),
    verification_method character varying(50),
    last_verified_at timestamp with time zone,
    evidence_note text,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_company_source_confidence CHECK (((confidence IS NULL) OR ((confidence >= (0)::numeric) AND (confidence <= (1)::numeric))))
);


--
-- Name: company_source_revision; Type: TABLE; Schema: company_radar; Owner: -
--

CREATE TABLE company_radar.company_source_revision (
    id uuid NOT NULL,
    company_source_id uuid NOT NULL,
    version integer NOT NULL,
    changed_at timestamp with time zone DEFAULT now() NOT NULL,
    changes jsonb NOT NULL,
    evidence_note text NOT NULL
);


--
-- Name: application_process; Type: TABLE; Schema: crm; Owner: -
--

CREATE TABLE crm.application_process (
    id uuid NOT NULL,
    opportunity_id uuid NOT NULL,
    profile_version_id uuid NOT NULL,
    current_stage character varying(16) NOT NULL,
    status character varying(16) DEFAULT 'ACTIVE'::character varying NOT NULL,
    outcome character varying(16),
    next_action character varying(500),
    next_action_at timestamp with time zone,
    notes text,
    applied_at timestamp with time zone,
    started_at timestamp with time zone NOT NULL,
    closed_at timestamp with time zone,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_application_closed_at CHECK ((((status)::text = 'CLOSED'::text) = (closed_at IS NOT NULL))),
    CONSTRAINT ck_application_closed_outcome CHECK ((((status)::text = 'CLOSED'::text) = (outcome IS NOT NULL))),
    CONSTRAINT ck_application_outcome CHECK (((outcome IS NULL) OR ((outcome)::text = ANY ((ARRAY['REJECTED'::character varying, 'WITHDRAWN'::character varying, 'CLOSED'::character varying])::text[])))),
    CONSTRAINT ck_application_stage CHECK (((current_stage)::text = ANY ((ARRAY['INTERESTED'::character varying, 'APPLIED'::character varying, 'SCREENING'::character varying, 'INTERVIEW'::character varying, 'TECHNICAL'::character varying, 'FINAL'::character varying, 'OFFER'::character varying, 'REJECTED'::character varying, 'WITHDRAWN'::character varying, 'CLOSED'::character varying])::text[]))),
    CONSTRAINT ck_application_status CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'CLOSED'::character varying])::text[]))),
    CONSTRAINT ck_application_version CHECK ((version > 0))
);


--
-- Name: stage_history; Type: TABLE; Schema: crm; Owner: -
--

CREATE TABLE crm.stage_history (
    id uuid NOT NULL,
    application_id uuid NOT NULL,
    from_stage character varying(16),
    to_stage character varying(16) NOT NULL,
    reason character varying(64),
    source character varying(16) DEFAULT 'MANUAL'::character varying NOT NULL,
    notes text,
    occurred_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_stage_history_from_stage CHECK (((from_stage IS NULL) OR ((from_stage)::text = ANY ((ARRAY['INTERESTED'::character varying, 'APPLIED'::character varying, 'SCREENING'::character varying, 'INTERVIEW'::character varying, 'TECHNICAL'::character varying, 'FINAL'::character varying, 'OFFER'::character varying, 'REJECTED'::character varying, 'WITHDRAWN'::character varying, 'CLOSED'::character varying])::text[])))),
    CONSTRAINT ck_stage_history_moves CHECK (((from_stage IS NULL) OR ((from_stage)::text <> (to_stage)::text))),
    CONSTRAINT ck_stage_history_source CHECK (((source)::text = ANY ((ARRAY['MANUAL'::character varying, 'SYSTEM'::character varying])::text[]))),
    CONSTRAINT ck_stage_history_to_stage CHECK (((to_stage)::text = ANY ((ARRAY['INTERESTED'::character varying, 'APPLIED'::character varying, 'SCREENING'::character varying, 'INTERVIEW'::character varying, 'TECHNICAL'::character varying, 'FINAL'::character varying, 'OFFER'::character varying, 'REJECTED'::character varying, 'WITHDRAWN'::character varying, 'CLOSED'::character varying])::text[])))
);


--
-- Name: match_analysis; Type: TABLE; Schema: matching; Owner: -
--

CREATE TABLE matching.match_analysis (
    id uuid NOT NULL,
    assessment_id uuid NOT NULL,
    cache_key character varying(64) NOT NULL,
    status character varying(16) NOT NULL,
    failure_code character varying(32),
    detail text,
    summary text,
    strengths jsonb DEFAULT '[]'::jsonb NOT NULL,
    risks jsonb DEFAULT '[]'::jsonb NOT NULL,
    inferences jsonb DEFAULT '[]'::jsonb NOT NULL,
    unknowns jsonb DEFAULT '[]'::jsonb NOT NULL,
    recommended_review boolean,
    model_id character varying(128),
    prompt_version character varying(64),
    schema_version character varying(32) NOT NULL,
    analyzed_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    total_ms integer,
    load_ms integer,
    prompt_tokens integer,
    prompt_eval_ms integer,
    output_tokens integer,
    eval_ms integer,
    prompt_chars integer,
    prompt_tokens_estimate integer,
    key_version character varying(32),
    payload_hash character varying(64),
    payload jsonb,
    inference jsonb,
    context_refs jsonb,
    prompt_budget integer,
    CONSTRAINT ck_match_analysis_cache_key CHECK ((char_length((cache_key)::text) = 64)),
    CONSTRAINT ck_match_analysis_completed_payload CHECK ((((status)::text <> 'AI_COMPLETED'::text) OR ((summary IS NOT NULL) AND (model_id IS NOT NULL) AND (recommended_review IS NOT NULL)))),
    CONSTRAINT ck_match_analysis_failed_code CHECK ((((status)::text <> 'AI_FAILED'::text) OR (failure_code IS NOT NULL))),
    CONSTRAINT ck_match_analysis_status CHECK (((status)::text = ANY ((ARRAY['AI_PENDING'::character varying, 'AI_COMPLETED'::character varying, 'AI_FAILED'::character varying, 'AI_SKIPPED'::character varying])::text[])))
);


--
-- Name: match_analysis_claim; Type: TABLE; Schema: matching; Owner: -
--

CREATE TABLE matching.match_analysis_claim (
    assessment_id uuid NOT NULL,
    owner character varying(64) NOT NULL,
    claimed_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_match_analysis_claim_window CHECK ((expires_at > claimed_at))
);


--
-- Name: match_assessment; Type: TABLE; Schema: matching; Owner: -
--

CREATE TABLE matching.match_assessment (
    id uuid NOT NULL,
    opportunity_id uuid NOT NULL,
    opportunity_version integer NOT NULL,
    profile_version_id uuid NOT NULL,
    input_hash character varying(64) NOT NULL,
    rules_version character varying(64) NOT NULL,
    taxonomy_version character varying(64) NOT NULL,
    opportunity_snapshot jsonb NOT NULL,
    profile_snapshot jsonb NOT NULL,
    eligibility character varying(16) NOT NULL,
    eligibility_details jsonb DEFAULT '[]'::jsonb NOT NULL,
    status character varying(16) DEFAULT 'COMPLETED'::character varying NOT NULL,
    verdict character varying(16) NOT NULL,
    score numeric(7,4) NOT NULL,
    confidence numeric(4,3) NOT NULL,
    assessed_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_match_assessment_confidence CHECK (((confidence >= (0)::numeric) AND (confidence <= (1)::numeric))),
    CONSTRAINT ck_match_assessment_eligibility CHECK (((eligibility)::text = ANY ((ARRAY['ELIGIBLE'::character varying, 'INELIGIBLE'::character varying, 'UNKNOWN'::character varying])::text[]))),
    CONSTRAINT ck_match_assessment_input_hash CHECK ((char_length((input_hash)::text) = 64)),
    CONSTRAINT ck_match_assessment_opportunity_version CHECK ((opportunity_version > 0)),
    CONSTRAINT ck_match_assessment_score CHECK (((score >= (0)::numeric) AND (score <= (100)::numeric))),
    CONSTRAINT ck_match_assessment_status CHECK (((status)::text = 'COMPLETED'::text)),
    CONSTRAINT ck_match_assessment_verdict CHECK (((verdict)::text = ANY ((ARRAY['HIGH_PRIORITY'::character varying, 'RECOMMENDED'::character varying, 'WATCHLIST'::character varying, 'LOW_MATCH'::character varying, 'INELIGIBLE'::character varying, 'REVIEW_REQUIRED'::character varying])::text[])))
);


--
-- Name: match_factor; Type: TABLE; Schema: matching; Owner: -
--

CREATE TABLE matching.match_factor (
    id uuid NOT NULL,
    assessment_id uuid NOT NULL,
    factor_code character varying(64) NOT NULL,
    weight numeric(5,4) NOT NULL,
    raw_score numeric(5,4),
    contribution numeric(7,4) NOT NULL,
    status character varying(16) NOT NULL,
    confidence numeric(4,3) NOT NULL,
    missing_policy character varying(32) NOT NULL,
    explanation text NOT NULL,
    evidence_refs jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_match_factor_confidence CHECK (((confidence >= (0)::numeric) AND (confidence <= (1)::numeric))),
    CONSTRAINT ck_match_factor_contribution CHECK (((contribution >= (0)::numeric) AND (contribution <= (100)::numeric))),
    CONSTRAINT ck_match_factor_missing_policy CHECK (((missing_policy)::text = ANY ((ARRAY['NEUTRAL'::character varying, 'PENALIZE'::character varying, 'EXCLUDE_AND_RENORMALIZE'::character varying, 'REQUIRE_REVIEW'::character varying])::text[]))),
    CONSTRAINT ck_match_factor_raw_score CHECK (((raw_score IS NULL) OR ((raw_score >= (0)::numeric) AND (raw_score <= (1)::numeric)))),
    CONSTRAINT ck_match_factor_status CHECK (((status)::text = ANY ((ARRAY['KNOWN'::character varying, 'UNKNOWN'::character varying, 'NOT_APPLICABLE'::character varying])::text[]))),
    CONSTRAINT ck_match_factor_weight CHECK (((weight >= (0)::numeric) AND (weight <= (1)::numeric)))
);


--
-- Name: normalization_result; Type: TABLE; Schema: opportunities; Owner: -
--

CREATE TABLE opportunities.normalization_result (
    id uuid NOT NULL,
    raw_item_id uuid NOT NULL,
    opportunity_id uuid,
    source_occurrence_id uuid,
    status character varying(16) NOT NULL,
    normalizer_version character varying(32) NOT NULL,
    identity_decision character varying(16),
    reasons jsonb DEFAULT '[]'::jsonb NOT NULL,
    error_summary text,
    processed_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_normalization_result_identity_decision CHECK (((identity_decision)::text = ANY ((ARRAY['NEW'::character varying, 'MERGED'::character varying, 'REFRESHED'::character varying, 'REVIEW'::character varying])::text[]))),
    CONSTRAINT ck_normalization_result_outcome CHECK (((((status)::text = 'FAILED'::text) AND (error_summary IS NOT NULL) AND (identity_decision IS NULL) AND (opportunity_id IS NULL) AND (source_occurrence_id IS NULL)) OR (((status)::text = ANY ((ARRAY['SUCCEEDED'::character varying, 'REVIEW_REQUIRED'::character varying])::text[])) AND (error_summary IS NULL) AND (identity_decision IS NOT NULL) AND (opportunity_id IS NOT NULL) AND (source_occurrence_id IS NOT NULL)))),
    CONSTRAINT ck_normalization_result_status CHECK (((status)::text = ANY ((ARRAY['SUCCEEDED'::character varying, 'REVIEW_REQUIRED'::character varying, 'FAILED'::character varying])::text[])))
);


--
-- Name: opportunity; Type: TABLE; Schema: opportunities; Owner: -
--

CREATE TABLE opportunities.opportunity (
    id uuid NOT NULL,
    fingerprint character varying(64) NOT NULL,
    fingerprint_version character varying(32) NOT NULL,
    canonical_title character varying(512) NOT NULL,
    normalized_title character varying(512) NOT NULL,
    canonical_company_id uuid,
    company_name character varying(255),
    normalized_company_name character varying(255),
    location_text character varying(512),
    normalized_location character varying(512),
    work_mode character varying(16) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    seniority character varying(16) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    contract_type character varying(16) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    description text,
    lifecycle_status character varying(16) DEFAULT 'DISCOVERED'::character varying NOT NULL,
    published_at timestamp with time zone,
    source_updated_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    closure_evidence jsonb,
    role_family character varying(32) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    role_family_evidence jsonb,
    role_family_version character varying(32),
    search_skills text,
    search_document tsvector GENERATED ALWAYS AS ((((((((((((setweight(to_tsvector('portuguese'::regconfig, opportunities.f_unaccent((COALESCE(canonical_title, ''::character varying))::text)), 'A'::"char") || setweight(to_tsvector('english'::regconfig, opportunities.f_unaccent((COALESCE(canonical_title, ''::character varying))::text)), 'A'::"char")) || setweight(to_tsvector('portuguese'::regconfig, opportunities.f_unaccent((COALESCE(company_name, ''::character varying))::text)), 'A'::"char")) || setweight(to_tsvector('english'::regconfig, opportunities.f_unaccent((COALESCE(company_name, ''::character varying))::text)), 'A'::"char")) || setweight(to_tsvector('portuguese'::regconfig, opportunities.f_unaccent(COALESCE(search_skills, ''::text))), 'B'::"char")) || setweight(to_tsvector('english'::regconfig, opportunities.f_unaccent(COALESCE(search_skills, ''::text))), 'B'::"char")) || setweight(to_tsvector('portuguese'::regconfig, opportunities.f_unaccent(replace((COALESCE(role_family, ''::character varying))::text, '_'::text, ' '::text))), 'B'::"char")) || setweight(to_tsvector('english'::regconfig, opportunities.f_unaccent(replace((COALESCE(role_family, ''::character varying))::text, '_'::text, ' '::text))), 'B'::"char")) || setweight(to_tsvector('portuguese'::regconfig, opportunities.f_unaccent(COALESCE(description, ''::text))), 'C'::"char")) || setweight(to_tsvector('english'::regconfig, opportunities.f_unaccent(COALESCE(description, ''::text))), 'C'::"char")) || setweight(to_tsvector('portuguese'::regconfig, opportunities.f_unaccent((COALESCE(location_text, ''::character varying))::text)), 'D'::"char")) || setweight(to_tsvector('english'::regconfig, opportunities.f_unaccent((COALESCE(location_text, ''::character varying))::text)), 'D'::"char"))) STORED,
    allowed_countries character varying(8)[],
    allowed_countries_version character varying(32),
    CONSTRAINT ck_opportunity_contract_type CHECK (((contract_type)::text = ANY ((ARRAY['FULL_TIME'::character varying, 'PART_TIME'::character varying, 'CONTRACT'::character varying, 'TEMPORARY'::character varying, 'INTERNSHIP'::character varying, 'UNKNOWN'::character varying])::text[]))),
    CONSTRAINT ck_opportunity_lifecycle_status CHECK (((lifecycle_status)::text = ANY ((ARRAY['DISCOVERED'::character varying, 'ACTIVE'::character varying, 'STALE'::character varying, 'CLOSED'::character varying, 'ARCHIVED'::character varying, 'REJECTED'::character varying])::text[]))),
    CONSTRAINT ck_opportunity_role_family CHECK (((role_family)::text = ANY ((ARRAY['SOFTWARE_ENGINEERING'::character varying, 'DATA'::character varying, 'INFRASTRUCTURE'::character varying, 'SECURITY'::character varying, 'QA'::character varying, 'PRODUCT'::character varying, 'DESIGN'::character varying, 'SALES'::character varying, 'MARKETING'::character varying, 'OPERATIONS'::character varying, 'PEOPLE'::character varying, 'FINANCE'::character varying, 'LEGAL'::character varying, 'SUPPORT'::character varying, 'OTHER'::character varying, 'UNKNOWN'::character varying])::text[]))),
    CONSTRAINT ck_opportunity_seniority CHECK (((seniority)::text = ANY ((ARRAY['INTERN'::character varying, 'JUNIOR'::character varying, 'MID'::character varying, 'SENIOR'::character varying, 'LEAD'::character varying, 'STAFF'::character varying, 'MANAGER'::character varying, 'DIRECTOR'::character varying, 'UNKNOWN'::character varying])::text[]))),
    CONSTRAINT ck_opportunity_version_positive CHECK ((version > 0)),
    CONSTRAINT ck_opportunity_work_mode CHECK (((work_mode)::text = ANY ((ARRAY['REMOTE'::character varying, 'HYBRID'::character varying, 'ONSITE'::character varying, 'UNKNOWN'::character varying])::text[])))
);


--
-- Name: opportunity_compensation; Type: TABLE; Schema: opportunities; Owner: -
--

CREATE TABLE opportunities.opportunity_compensation (
    id uuid NOT NULL,
    opportunity_id uuid NOT NULL,
    amount_min numeric(14,2),
    amount_max numeric(14,2),
    currency character varying(3),
    period character varying(16) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    gross_net character varying(16) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    evidence_text text,
    evidence_source character varying(512),
    normalizer_version character varying(32) NOT NULL,
    source_occurrence_id uuid NOT NULL,
    raw_item_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_opportunity_compensation_amount_present CHECK (((amount_min IS NOT NULL) OR (amount_max IS NOT NULL))),
    CONSTRAINT ck_opportunity_compensation_gross_net CHECK (((gross_net)::text = ANY ((ARRAY['GROSS'::character varying, 'NET'::character varying, 'UNKNOWN'::character varying])::text[]))),
    CONSTRAINT ck_opportunity_compensation_period CHECK (((period)::text = ANY ((ARRAY['YEAR'::character varying, 'MONTH'::character varying, 'WEEK'::character varying, 'DAY'::character varying, 'HOUR'::character varying, 'UNKNOWN'::character varying])::text[]))),
    CONSTRAINT ck_opportunity_compensation_range CHECK (((amount_min IS NULL) OR (amount_max IS NULL) OR (amount_min <= amount_max)))
);


--
-- Name: opportunity_embedding; Type: TABLE; Schema: opportunities; Owner: -
--

CREATE TABLE opportunities.opportunity_embedding (
    opportunity_id uuid NOT NULL,
    content_version integer NOT NULL,
    model character varying(128) NOT NULL,
    text_version character varying(64) NOT NULL,
    text_hash character(64) NOT NULL,
    dimensions integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    embedding public.vector(1024) NOT NULL,
    CONSTRAINT ck_opportunity_embedding_content_version CHECK ((content_version > 0)),
    CONSTRAINT ck_opportunity_embedding_dimensions CHECK ((dimensions > 0)),
    CONSTRAINT ck_opportunity_embedding_text_hash CHECK ((char_length(text_hash) = 64))
);


--
-- Name: opportunity_embedding_failure; Type: TABLE; Schema: opportunities; Owner: -
--

CREATE TABLE opportunities.opportunity_embedding_failure (
    opportunity_id uuid NOT NULL,
    content_version integer NOT NULL,
    model character varying(128) NOT NULL,
    text_version character varying(64) NOT NULL,
    failure_code character varying(32) NOT NULL,
    detail text,
    attempts integer DEFAULT 1 NOT NULL,
    first_failed_at timestamp with time zone DEFAULT now() NOT NULL,
    last_attempt_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_opportunity_embedding_failure_attempts CHECK ((attempts > 0))
);


--
-- Name: opportunity_skill; Type: TABLE; Schema: opportunities; Owner: -
--

CREATE TABLE opportunities.opportunity_skill (
    id uuid NOT NULL,
    opportunity_id uuid NOT NULL,
    canonical_name character varying(128) NOT NULL,
    display_name character varying(128) NOT NULL,
    requirement character varying(16) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    evidence jsonb DEFAULT '[]'::jsonb NOT NULL,
    taxonomy_version character varying(32) NOT NULL,
    normalizer_version character varying(32) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_opportunity_skill_requirement CHECK (((requirement)::text = ANY ((ARRAY['REQUIRED'::character varying, 'PREFERRED'::character varying, 'UNKNOWN'::character varying])::text[])))
);


--
-- Name: relevance_mark; Type: TABLE; Schema: opportunities; Owner: -
--

CREATE TABLE opportunities.relevance_mark (
    id uuid NOT NULL,
    opportunity_id uuid NOT NULL,
    relevant boolean NOT NULL,
    reason character varying(16),
    note text,
    profile_version_id uuid,
    marked_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_relevance_mark_reason CHECK (((reason IS NULL) OR ((reason)::text = ANY ((ARRAY['AREA'::character varying, 'SENIORITY'::character varying, 'LOCATION'::character varying, 'COMPANY'::character varying, 'COMPENSATION'::character varying, 'OTHER'::character varying])::text[]))))
);


--
-- Name: source_occurrence; Type: TABLE; Schema: opportunities; Owner: -
--

CREATE TABLE opportunities.source_occurrence (
    id uuid NOT NULL,
    opportunity_id uuid NOT NULL,
    raw_item_id uuid NOT NULL,
    source_definition_id uuid NOT NULL,
    external_id character varying(512),
    source_url character varying(2048),
    normalized_source_url character varying(2048),
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    source_published_at timestamp with time zone,
    source_updated_at timestamp with time zone,
    last_seen_run_id uuid
);


--
-- Name: worker_job_state; Type: TABLE; Schema: platform; Owner: -
--

CREATE TABLE platform.worker_job_state (
    job_name character varying(64) NOT NULL,
    last_attempt_at timestamp with time zone NOT NULL,
    last_success_at timestamp with time zone,
    last_failure_at timestamp with time zone,
    last_duration_ms integer,
    next_run_at timestamp with time zone NOT NULL,
    last_correlation_id character varying(64) NOT NULL,
    last_error text
);


--
-- Name: career_profile; Type: TABLE; Schema: profile; Owner: -
--

CREATE TABLE profile.career_profile (
    id uuid NOT NULL,
    singleton_key boolean DEFAULT true NOT NULL,
    version integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_career_profile_singleton CHECK (singleton_key)
);


--
-- Name: employment_preference; Type: TABLE; Schema: profile; Owner: -
--

CREATE TABLE profile.employment_preference (
    id uuid NOT NULL,
    profile_version_id uuid NOT NULL,
    work_modes character varying[] DEFAULT '{}'::character varying[] NOT NULL,
    contracts character varying[] DEFAULT '{}'::character varying[] NOT NULL,
    countries character varying[] DEFAULT '{}'::character varying[] NOT NULL,
    timezone_start_hour integer,
    timezone_end_hour integer,
    compensation_min numeric(14,2),
    compensation_max numeric(14,2),
    compensation_currency character varying(3),
    relocation_allowed boolean DEFAULT false NOT NULL,
    sponsorship_required boolean DEFAULT false NOT NULL,
    compensation_period character varying(16),
    target_role_families character varying(32)[] DEFAULT '{}'::character varying[] NOT NULL,
    CONSTRAINT ck_preference_compensation CHECK (((compensation_min IS NULL) OR (compensation_max IS NULL) OR (compensation_min <= compensation_max))),
    CONSTRAINT ck_preference_compensation_period CHECK (((compensation_period IS NULL) OR ((compensation_period)::text = ANY ((ARRAY['YEAR'::character varying, 'MONTH'::character varying, 'WEEK'::character varying, 'DAY'::character varying, 'HOUR'::character varying])::text[])))),
    CONSTRAINT ck_preference_timezone CHECK ((((timezone_start_hour IS NULL) AND (timezone_end_hour IS NULL)) OR ((timezone_start_hour IS NOT NULL) AND (timezone_end_hour IS NOT NULL) AND (timezone_start_hour >= 0) AND (timezone_start_hour < timezone_end_hour) AND (timezone_end_hour <= 23))))
);


--
-- Name: experience; Type: TABLE; Schema: profile; Owner: -
--

CREATE TABLE profile.experience (
    id uuid NOT NULL,
    profile_version_id uuid NOT NULL,
    company_name character varying(256) NOT NULL,
    title character varying(256) NOT NULL,
    started_on date NOT NULL,
    ended_on date,
    summary text,
    CONSTRAINT ck_experience_dates CHECK (((ended_on IS NULL) OR (ended_on >= started_on)))
);


--
-- Name: profile_skill; Type: TABLE; Schema: profile; Owner: -
--

CREATE TABLE profile.profile_skill (
    id uuid NOT NULL,
    profile_version_id uuid NOT NULL,
    skill_id uuid NOT NULL,
    level character varying(32),
    last_used_at date,
    experience_months integer,
    CONSTRAINT ck_profile_skill_months CHECK (((experience_months IS NULL) OR (experience_months >= 0)))
);


--
-- Name: profile_version; Type: TABLE; Schema: profile; Owner: -
--

CREATE TABLE profile.profile_version (
    id uuid NOT NULL,
    career_profile_id uuid NOT NULL,
    number integer NOT NULL,
    status character varying(16) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    published_at timestamp with time zone,
    activated_at timestamp with time zone,
    CONSTRAINT ck_profile_version_status CHECK (((status)::text = ANY ((ARRAY['DRAFT'::character varying, 'PUBLISHED'::character varying, 'ACTIVE'::character varying, 'ARCHIVED'::character varying])::text[])))
);


--
-- Name: project; Type: TABLE; Schema: profile; Owner: -
--

CREATE TABLE profile.project (
    id uuid NOT NULL,
    profile_version_id uuid NOT NULL,
    name character varying(256) NOT NULL,
    started_on date,
    ended_on date,
    description text,
    url character varying(2048),
    CONSTRAINT ck_project_dates CHECK (((ended_on IS NULL) OR (started_on IS NULL) OR (ended_on >= started_on)))
);


--
-- Name: skill; Type: TABLE; Schema: profile; Owner: -
--

CREATE TABLE profile.skill (
    id uuid NOT NULL,
    canonical_name character varying(128) NOT NULL,
    display_name character varying(128) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Data for Name: payload_retention_event; Type: TABLE DATA; Schema: acquisition; Owner: -
--

COPY acquisition.payload_retention_event (id, raw_item_id, expired_at, retention_policy_version, retention_days, payload_hash, source_definition_id) FROM stdin;
\.


--
-- Data for Name: raw_item; Type: TABLE DATA; Schema: acquisition; Owner: -
--

COPY acquisition.raw_item (id, source_run_id, source_definition_id, external_id, canonical_url, identity_key, payload_hash, content_type, fetched_at, parser_version, metadata) FROM stdin;
ca12553c-e8ba-4220-ab51-39fd091bdc0d	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:660070ed895ce85432bd51a75bad92b7bbe866b68de5d28aebe2dc146681e269	https://example.com/jobs/fixture-1	external:manual:660070ed895ce85432bd51a75bad92b7bbe866b68de5d28aebe2dc146681e269	660070ed895ce85432bd51a75bad92b7bbe866b68de5d28aebe2dc146681e269	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 1", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 1", "collected_item_v1": {"url": "https://example.com/jobs/fixture-1", "title": "Backend Engineer 1", "version": 1, "metadata": {"title": "Backend Engineer 1", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 1"}, "updated_at": null, "description": null, "external_id": "manual:660070ed895ce85432bd51a75bad92b7bbe866b68de5d28aebe2dc146681e269", "source_type": "manual", "company_name": "Fixture Co 1", "published_at": null, "location_text": null, "parser_version": null}}
388fd30a-292b-4128-88f4-c7d808828dfa	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:030a31257f065474abe57b1fba4b67152dc586f8cf51c1c6a1e9f54c014eda23	https://example.com/jobs/fixture-2	external:manual:030a31257f065474abe57b1fba4b67152dc586f8cf51c1c6a1e9f54c014eda23	030a31257f065474abe57b1fba4b67152dc586f8cf51c1c6a1e9f54c014eda23	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 2", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 2", "collected_item_v1": {"url": "https://example.com/jobs/fixture-2", "title": "Backend Engineer 2", "version": 1, "metadata": {"title": "Backend Engineer 2", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 2"}, "updated_at": null, "description": null, "external_id": "manual:030a31257f065474abe57b1fba4b67152dc586f8cf51c1c6a1e9f54c014eda23", "source_type": "manual", "company_name": "Fixture Co 2", "published_at": null, "location_text": null, "parser_version": null}}
19a81372-2092-4385-9b5f-0388cee53e81	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:71209897cdea7a33d788be4131e04e526a866735ff44958dbcf3d297ddbe6800	https://example.com/jobs/fixture-3	external:manual:71209897cdea7a33d788be4131e04e526a866735ff44958dbcf3d297ddbe6800	71209897cdea7a33d788be4131e04e526a866735ff44958dbcf3d297ddbe6800	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 3", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 3", "collected_item_v1": {"url": "https://example.com/jobs/fixture-3", "title": "Backend Engineer 3", "version": 1, "metadata": {"title": "Backend Engineer 3", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 3"}, "updated_at": null, "description": null, "external_id": "manual:71209897cdea7a33d788be4131e04e526a866735ff44958dbcf3d297ddbe6800", "source_type": "manual", "company_name": "Fixture Co 3", "published_at": null, "location_text": null, "parser_version": null}}
ae475ec9-60db-4ba8-a5f5-3ce782d31ba8	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:06401d67faeeb840296203b157354ca312d8062a5d2badf760aa0f3e238761d0	https://example.com/jobs/fixture-4	external:manual:06401d67faeeb840296203b157354ca312d8062a5d2badf760aa0f3e238761d0	06401d67faeeb840296203b157354ca312d8062a5d2badf760aa0f3e238761d0	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 4", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 4", "collected_item_v1": {"url": "https://example.com/jobs/fixture-4", "title": "Backend Engineer 4", "version": 1, "metadata": {"title": "Backend Engineer 4", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 4"}, "updated_at": null, "description": null, "external_id": "manual:06401d67faeeb840296203b157354ca312d8062a5d2badf760aa0f3e238761d0", "source_type": "manual", "company_name": "Fixture Co 4", "published_at": null, "location_text": null, "parser_version": null}}
f129b7e1-36bc-425a-b971-01ade87c32fd	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:0ac97018a871e19176b044e5b34b1720192de0dfc3efd9badb0bb97faca8fa44	https://example.com/jobs/fixture-5	external:manual:0ac97018a871e19176b044e5b34b1720192de0dfc3efd9badb0bb97faca8fa44	0ac97018a871e19176b044e5b34b1720192de0dfc3efd9badb0bb97faca8fa44	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 5", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 5", "collected_item_v1": {"url": "https://example.com/jobs/fixture-5", "title": "Backend Engineer 5", "version": 1, "metadata": {"title": "Backend Engineer 5", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 5"}, "updated_at": null, "description": null, "external_id": "manual:0ac97018a871e19176b044e5b34b1720192de0dfc3efd9badb0bb97faca8fa44", "source_type": "manual", "company_name": "Fixture Co 5", "published_at": null, "location_text": null, "parser_version": null}}
f33ac04f-b48f-4216-bbd6-5f9bcf539907	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:63bbebc4e764b6b4d53f9e0a86db183a89f4bb9df34fb9d3da6a48dea0ada4e9	https://example.com/jobs/fixture-6	external:manual:63bbebc4e764b6b4d53f9e0a86db183a89f4bb9df34fb9d3da6a48dea0ada4e9	63bbebc4e764b6b4d53f9e0a86db183a89f4bb9df34fb9d3da6a48dea0ada4e9	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 6", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 6", "collected_item_v1": {"url": "https://example.com/jobs/fixture-6", "title": "Backend Engineer 6", "version": 1, "metadata": {"title": "Backend Engineer 6", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 6"}, "updated_at": null, "description": null, "external_id": "manual:63bbebc4e764b6b4d53f9e0a86db183a89f4bb9df34fb9d3da6a48dea0ada4e9", "source_type": "manual", "company_name": "Fixture Co 6", "published_at": null, "location_text": null, "parser_version": null}}
e967f036-6280-4f34-b6ff-7befdfc8d318	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:20181322df4dea864afcd94a9f80e04c7374b1a60a6a81fb4f4dcdb753fb9bfd	https://example.com/jobs/fixture-7	external:manual:20181322df4dea864afcd94a9f80e04c7374b1a60a6a81fb4f4dcdb753fb9bfd	20181322df4dea864afcd94a9f80e04c7374b1a60a6a81fb4f4dcdb753fb9bfd	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 7", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 7", "collected_item_v1": {"url": "https://example.com/jobs/fixture-7", "title": "Backend Engineer 7", "version": 1, "metadata": {"title": "Backend Engineer 7", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 7"}, "updated_at": null, "description": null, "external_id": "manual:20181322df4dea864afcd94a9f80e04c7374b1a60a6a81fb4f4dcdb753fb9bfd", "source_type": "manual", "company_name": "Fixture Co 7", "published_at": null, "location_text": null, "parser_version": null}}
dfad672c-01cf-49bd-91a7-7c39211e0dfb	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:b2224cdc97235adf062a0b3a4d97df162c5a32746cfb00e480d477cda326b0a0	https://example.com/jobs/fixture-8	external:manual:b2224cdc97235adf062a0b3a4d97df162c5a32746cfb00e480d477cda326b0a0	b2224cdc97235adf062a0b3a4d97df162c5a32746cfb00e480d477cda326b0a0	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 8", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 8", "collected_item_v1": {"url": "https://example.com/jobs/fixture-8", "title": "Backend Engineer 8", "version": 1, "metadata": {"title": "Backend Engineer 8", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 8"}, "updated_at": null, "description": null, "external_id": "manual:b2224cdc97235adf062a0b3a4d97df162c5a32746cfb00e480d477cda326b0a0", "source_type": "manual", "company_name": "Fixture Co 8", "published_at": null, "location_text": null, "parser_version": null}}
4d7cfa7b-2c02-442b-8339-9361412c006e	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:05c3586acd0d9d08fd5d1e0b1ef57b2efde38c9a777c94ceaa446e8775f99269	https://example.com/jobs/fixture-9	external:manual:05c3586acd0d9d08fd5d1e0b1ef57b2efde38c9a777c94ceaa446e8775f99269	05c3586acd0d9d08fd5d1e0b1ef57b2efde38c9a777c94ceaa446e8775f99269	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 9", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 9", "collected_item_v1": {"url": "https://example.com/jobs/fixture-9", "title": "Backend Engineer 9", "version": 1, "metadata": {"title": "Backend Engineer 9", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 9"}, "updated_at": null, "description": null, "external_id": "manual:05c3586acd0d9d08fd5d1e0b1ef57b2efde38c9a777c94ceaa446e8775f99269", "source_type": "manual", "company_name": "Fixture Co 9", "published_at": null, "location_text": null, "parser_version": null}}
e169598b-42d5-4267-97fb-ea83d2f49ac8	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:7daa647023aaf2b6c18f60120f2a37177b3aab59e02f82e2a4a350d2f9f47db1	https://example.com/jobs/fixture-10	external:manual:7daa647023aaf2b6c18f60120f2a37177b3aab59e02f82e2a4a350d2f9f47db1	7daa647023aaf2b6c18f60120f2a37177b3aab59e02f82e2a4a350d2f9f47db1	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 10", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 10", "collected_item_v1": {"url": "https://example.com/jobs/fixture-10", "title": "Backend Engineer 10", "version": 1, "metadata": {"title": "Backend Engineer 10", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 10"}, "updated_at": null, "description": null, "external_id": "manual:7daa647023aaf2b6c18f60120f2a37177b3aab59e02f82e2a4a350d2f9f47db1", "source_type": "manual", "company_name": "Fixture Co 10", "published_at": null, "location_text": null, "parser_version": null}}
b092dfbc-4e40-4399-9f75-c577d698e8b4	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:d0bd0e5b4c32b809ec9289322a16c1667bd405385f0ac8102b9b6af6004acefb	https://example.com/jobs/fixture-11	external:manual:d0bd0e5b4c32b809ec9289322a16c1667bd405385f0ac8102b9b6af6004acefb	d0bd0e5b4c32b809ec9289322a16c1667bd405385f0ac8102b9b6af6004acefb	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 11", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 11", "collected_item_v1": {"url": "https://example.com/jobs/fixture-11", "title": "Backend Engineer 11", "version": 1, "metadata": {"title": "Backend Engineer 11", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 11"}, "updated_at": null, "description": null, "external_id": "manual:d0bd0e5b4c32b809ec9289322a16c1667bd405385f0ac8102b9b6af6004acefb", "source_type": "manual", "company_name": "Fixture Co 11", "published_at": null, "location_text": null, "parser_version": null}}
818b70a4-9057-4d51-b19c-832c8c2bf892	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:a0b605271e219aa0ef4e53e0870a15d88a70cfb5e06b7b9a2189c531d6da22f7	https://example.com/jobs/fixture-12	external:manual:a0b605271e219aa0ef4e53e0870a15d88a70cfb5e06b7b9a2189c531d6da22f7	a0b605271e219aa0ef4e53e0870a15d88a70cfb5e06b7b9a2189c531d6da22f7	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 12", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 12", "collected_item_v1": {"url": "https://example.com/jobs/fixture-12", "title": "Backend Engineer 12", "version": 1, "metadata": {"title": "Backend Engineer 12", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 12"}, "updated_at": null, "description": null, "external_id": "manual:a0b605271e219aa0ef4e53e0870a15d88a70cfb5e06b7b9a2189c531d6da22f7", "source_type": "manual", "company_name": "Fixture Co 12", "published_at": null, "location_text": null, "parser_version": null}}
9a2bb19b-7935-4087-84bb-1af773401c4f	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:b786102d1858ff6ca43c3f0b695e2da49291adeda5f6745d8c7f684a11be27e9	https://example.com/jobs/fixture-13	external:manual:b786102d1858ff6ca43c3f0b695e2da49291adeda5f6745d8c7f684a11be27e9	b786102d1858ff6ca43c3f0b695e2da49291adeda5f6745d8c7f684a11be27e9	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 13", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 13", "collected_item_v1": {"url": "https://example.com/jobs/fixture-13", "title": "Backend Engineer 13", "version": 1, "metadata": {"title": "Backend Engineer 13", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 13"}, "updated_at": null, "description": null, "external_id": "manual:b786102d1858ff6ca43c3f0b695e2da49291adeda5f6745d8c7f684a11be27e9", "source_type": "manual", "company_name": "Fixture Co 13", "published_at": null, "location_text": null, "parser_version": null}}
310610b2-1e99-4e78-bedd-d364383c35f2	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:42b3a95cc10610805faceb52dc5e5776b0cf26c1b2692568c01768a9d814c06b	https://example.com/jobs/fixture-14	external:manual:42b3a95cc10610805faceb52dc5e5776b0cf26c1b2692568c01768a9d814c06b	42b3a95cc10610805faceb52dc5e5776b0cf26c1b2692568c01768a9d814c06b	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 14", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 14", "collected_item_v1": {"url": "https://example.com/jobs/fixture-14", "title": "Backend Engineer 14", "version": 1, "metadata": {"title": "Backend Engineer 14", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 14"}, "updated_at": null, "description": null, "external_id": "manual:42b3a95cc10610805faceb52dc5e5776b0cf26c1b2692568c01768a9d814c06b", "source_type": "manual", "company_name": "Fixture Co 14", "published_at": null, "location_text": null, "parser_version": null}}
c6e2a518-f82e-4a0e-9f10-c9fd035795eb	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:3e31cdb1e9b7fb0a0ef2396e57301faafc3de74b5c9426d7402709a5a09cfb0f	https://example.com/jobs/fixture-15	external:manual:3e31cdb1e9b7fb0a0ef2396e57301faafc3de74b5c9426d7402709a5a09cfb0f	3e31cdb1e9b7fb0a0ef2396e57301faafc3de74b5c9426d7402709a5a09cfb0f	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 15", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 15", "collected_item_v1": {"url": "https://example.com/jobs/fixture-15", "title": "Backend Engineer 15", "version": 1, "metadata": {"title": "Backend Engineer 15", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 15"}, "updated_at": null, "description": null, "external_id": "manual:3e31cdb1e9b7fb0a0ef2396e57301faafc3de74b5c9426d7402709a5a09cfb0f", "source_type": "manual", "company_name": "Fixture Co 15", "published_at": null, "location_text": null, "parser_version": null}}
ff51a452-8ba7-434f-b9d6-f1f841726c80	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:fd796cb9a7332eec5ea0947c141f790468b38f4f39dbbd7591aed815bd4a6b74	https://example.com/jobs/fixture-16	external:manual:fd796cb9a7332eec5ea0947c141f790468b38f4f39dbbd7591aed815bd4a6b74	fd796cb9a7332eec5ea0947c141f790468b38f4f39dbbd7591aed815bd4a6b74	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 16", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 16", "collected_item_v1": {"url": "https://example.com/jobs/fixture-16", "title": "Backend Engineer 16", "version": 1, "metadata": {"title": "Backend Engineer 16", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 16"}, "updated_at": null, "description": null, "external_id": "manual:fd796cb9a7332eec5ea0947c141f790468b38f4f39dbbd7591aed815bd4a6b74", "source_type": "manual", "company_name": "Fixture Co 16", "published_at": null, "location_text": null, "parser_version": null}}
bc90a2a2-91db-4e49-97ab-bf19066397a2	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:be625f5041c178b85e75a0916ab71a7dd13e20ae583cfb52bf6f766bd0172da9	https://example.com/jobs/fixture-17	external:manual:be625f5041c178b85e75a0916ab71a7dd13e20ae583cfb52bf6f766bd0172da9	be625f5041c178b85e75a0916ab71a7dd13e20ae583cfb52bf6f766bd0172da9	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 17", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 17", "collected_item_v1": {"url": "https://example.com/jobs/fixture-17", "title": "Backend Engineer 17", "version": 1, "metadata": {"title": "Backend Engineer 17", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 17"}, "updated_at": null, "description": null, "external_id": "manual:be625f5041c178b85e75a0916ab71a7dd13e20ae583cfb52bf6f766bd0172da9", "source_type": "manual", "company_name": "Fixture Co 17", "published_at": null, "location_text": null, "parser_version": null}}
005a6afe-f63e-4bb8-be0b-5fd2724742ec	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:5849c08da41a8433844df1d59e04533df57d9b95f94c0b59c8ba1c79aea50b83	https://example.com/jobs/fixture-18	external:manual:5849c08da41a8433844df1d59e04533df57d9b95f94c0b59c8ba1c79aea50b83	5849c08da41a8433844df1d59e04533df57d9b95f94c0b59c8ba1c79aea50b83	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 18", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 18", "collected_item_v1": {"url": "https://example.com/jobs/fixture-18", "title": "Backend Engineer 18", "version": 1, "metadata": {"title": "Backend Engineer 18", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 18"}, "updated_at": null, "description": null, "external_id": "manual:5849c08da41a8433844df1d59e04533df57d9b95f94c0b59c8ba1c79aea50b83", "source_type": "manual", "company_name": "Fixture Co 18", "published_at": null, "location_text": null, "parser_version": null}}
49b4b3a7-be04-4077-8a3a-634ce5b9cd02	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:b12129a4d89404aa0d6183fe41911719e491ad477651ab33c1ef676673472f78	https://example.com/jobs/fixture-19	external:manual:b12129a4d89404aa0d6183fe41911719e491ad477651ab33c1ef676673472f78	b12129a4d89404aa0d6183fe41911719e491ad477651ab33c1ef676673472f78	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 19", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 19", "collected_item_v1": {"url": "https://example.com/jobs/fixture-19", "title": "Backend Engineer 19", "version": 1, "metadata": {"title": "Backend Engineer 19", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 19"}, "updated_at": null, "description": null, "external_id": "manual:b12129a4d89404aa0d6183fe41911719e491ad477651ab33c1ef676673472f78", "source_type": "manual", "company_name": "Fixture Co 19", "published_at": null, "location_text": null, "parser_version": null}}
1c07155c-5c37-44d7-83ff-a4ea4ff9cb48	e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:5c6a0436a40fa7213c38747aa775bc5fa731a3d70b4575489fa70ccad0776bbf	https://example.com/jobs/fixture-20	external:manual:5c6a0436a40fa7213c38747aa775bc5fa731a3d70b4575489fa70ccad0776bbf	5c6a0436a40fa7213c38747aa775bc5fa731a3d70b4575489fa70ccad0776bbf	\N	2026-09-27 14:12:24.805155+00	\N	{"title": "Backend Engineer 20", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 20", "collected_item_v1": {"url": "https://example.com/jobs/fixture-20", "title": "Backend Engineer 20", "version": 1, "metadata": {"title": "Backend Engineer 20", "description": "Synthetic fixture job posting for F20-48 upgrade proof. Python, SQL, remote, mid-level.", "company_name": "Fixture Co 20"}, "updated_at": null, "description": null, "external_id": "manual:5c6a0436a40fa7213c38747aa775bc5fa731a3d70b4575489fa70ccad0776bbf", "source_type": "manual", "company_name": "Fixture Co 20", "published_at": null, "location_text": null, "parser_version": null}}
\.


--
-- Data for Name: raw_item_payload; Type: TABLE DATA; Schema: acquisition; Owner: -
--

COPY acquisition.raw_item_payload (raw_item_id, payload, stored_at, expired_at, retention_policy_version) FROM stdin;
ca12553c-e8ba-4220-ab51-39fd091bdc0d	{"url": "https://example.com/jobs/fixture-1", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
388fd30a-292b-4128-88f4-c7d808828dfa	{"url": "https://example.com/jobs/fixture-2", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
19a81372-2092-4385-9b5f-0388cee53e81	{"url": "https://example.com/jobs/fixture-3", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
ae475ec9-60db-4ba8-a5f5-3ce782d31ba8	{"url": "https://example.com/jobs/fixture-4", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
f129b7e1-36bc-425a-b971-01ade87c32fd	{"url": "https://example.com/jobs/fixture-5", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
f33ac04f-b48f-4216-bbd6-5f9bcf539907	{"url": "https://example.com/jobs/fixture-6", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
e967f036-6280-4f34-b6ff-7befdfc8d318	{"url": "https://example.com/jobs/fixture-7", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
dfad672c-01cf-49bd-91a7-7c39211e0dfb	{"url": "https://example.com/jobs/fixture-8", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
4d7cfa7b-2c02-442b-8339-9361412c006e	{"url": "https://example.com/jobs/fixture-9", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
e169598b-42d5-4267-97fb-ea83d2f49ac8	{"url": "https://example.com/jobs/fixture-10", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
b092dfbc-4e40-4399-9f75-c577d698e8b4	{"url": "https://example.com/jobs/fixture-11", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
818b70a4-9057-4d51-b19c-832c8c2bf892	{"url": "https://example.com/jobs/fixture-12", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
9a2bb19b-7935-4087-84bb-1af773401c4f	{"url": "https://example.com/jobs/fixture-13", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
310610b2-1e99-4e78-bedd-d364383c35f2	{"url": "https://example.com/jobs/fixture-14", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
c6e2a518-f82e-4a0e-9f10-c9fd035795eb	{"url": "https://example.com/jobs/fixture-15", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
ff51a452-8ba7-434f-b9d6-f1f841726c80	{"url": "https://example.com/jobs/fixture-16", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
bc90a2a2-91db-4e49-97ab-bf19066397a2	{"url": "https://example.com/jobs/fixture-17", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
005a6afe-f63e-4bb8-be0b-5fd2724742ec	{"url": "https://example.com/jobs/fixture-18", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
49b4b3a7-be04-4077-8a3a-634ce5b9cd02	{"url": "https://example.com/jobs/fixture-19", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
1c07155c-5c37-44d7-83ff-a4ea4ff9cb48	{"url": "https://example.com/jobs/fixture-20", "kind": "URL"}	2026-09-27 14:12:24.805155+00	\N	\N
\.


--
-- Data for Name: source_alert_incident; Type: TABLE DATA; Schema: acquisition; Owner: -
--

COPY acquisition.source_alert_incident (id, source_definition_id, opened_at, opened_by_run_id, consecutive_failures, error_code, error_summary, alert_sent_at, alert_delivery, recovered_at, recovered_by_run_id, recovery_sent_at, recovery_delivery, correlation_id) FROM stdin;
\.


--
-- Data for Name: source_checkpoint; Type: TABLE DATA; Schema: acquisition; Owner: -
--

COPY acquisition.source_checkpoint (source_definition_id, checkpoint_type, cursor, updated_since, etag, last_modified, promoted_by_run_id, promoted_at) FROM stdin;
\.


--
-- Data for Name: source_definition; Type: TABLE DATA; Schema: acquisition; Owner: -
--

COPY acquisition.source_definition (id, company_source_id, source_type, name, enabled, schedule, priority, rate_limit_policy, configuration, evidence_status, reviewed_at, terms_reviewed, collector_local_tested, last_health_status, created_at, updated_at, version, last_http_attempt_at) FROM stdin;
70fc1c6e-df43-41fe-a141-71cc15469cbf	\N	manual	F20-48 fixture source	t	\N	100	{}	{}	confirmed	\N	f	t	\N	2026-09-27 14:11:49.769908+00	2026-09-27 14:11:49.769908+00	1	\N
\.


--
-- Data for Name: source_probe; Type: TABLE DATA; Schema: acquisition; Owner: -
--

COPY acquisition.source_probe (id, source_definition_id, requested_by, status, started_at, finished_at, items_seen, http_requests, error_code, detail, evidence_recorded) FROM stdin;
\.


--
-- Data for Name: source_run; Type: TABLE DATA; Schema: acquisition; Owner: -
--

COPY acquisition.source_run (id, source_definition_id, status, started_at, finished_at, items_seen, items_persisted, items_skipped, items_invalid, http_requests, retry_count, error_code, error_summary, checkpoint_before, checkpoint_after, correlation_id, rate_limit_events, execution_trigger, items_announced, complete) FROM stdin;
e28ae9d8-50a0-4603-9c28-a0172362188c	70fc1c6e-df43-41fe-a141-71cc15469cbf	SUCCEEDED	2026-09-27 14:12:24.816713+00	2026-09-27 14:12:25.05968+00	20	20	0	0	0	0	\N	\N	\N	\N	\N	0	ON_DEMAND	\N	t
\.


--
-- Data for Name: company; Type: TABLE DATA; Schema: company_radar; Owner: -
--

COPY company_radar.company (id, canonical_name, normalized_name, domain, priority, radar_status, verification_state, created_at, updated_at, version) FROM stdin;
\.


--
-- Data for Name: company_alias; Type: TABLE DATA; Schema: company_radar; Owner: -
--

COPY company_radar.company_alias (id, company_id, alias, normalized_alias) FROM stdin;
\.


--
-- Data for Name: company_import_batch; Type: TABLE DATA; Schema: company_radar; Owner: -
--

COPY company_radar.company_import_batch (id, file_hash, source_filename, status, report, created_at, completed_at) FROM stdin;
\.


--
-- Data for Name: company_import_issue; Type: TABLE DATA; Schema: company_radar; Owner: -
--

COPY company_radar.company_import_issue (id, batch_id, row_number, code, message, raw_data) FROM stdin;
\.


--
-- Data for Name: company_source; Type: TABLE DATA; Schema: company_radar; Owner: -
--

COPY company_radar.company_source (id, company_id, source_type, endpoint, external_key, verification_status, confidence, verification_method, last_verified_at, evidence_note, version, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: company_source_revision; Type: TABLE DATA; Schema: company_radar; Owner: -
--

COPY company_radar.company_source_revision (id, company_source_id, version, changed_at, changes, evidence_note) FROM stdin;
\.


--
-- Data for Name: application_process; Type: TABLE DATA; Schema: crm; Owner: -
--

COPY crm.application_process (id, opportunity_id, profile_version_id, current_stage, status, outcome, next_action, next_action_at, notes, applied_at, started_at, closed_at, version, created_at, updated_at) FROM stdin;
2ef80276-985c-4819-a083-b9293a20b17f	bee90be5-75fe-427d-8d6d-e8e6e47a327c	ba87f661-4299-4fdd-bc69-12f182e3e2dc	APPLIED	ACTIVE	\N	\N	\N	\N	\N	2026-09-27 14:14:19.240537+00	\N	1	2026-09-27 14:14:19.240537+00	2026-09-27 14:14:19.240537+00
e152d977-fb7c-4c59-9981-c6ff28de54ab	19f8b07d-e01e-4034-bee9-a3b50cdfbca9	ba87f661-4299-4fdd-bc69-12f182e3e2dc	APPLIED	ACTIVE	\N	\N	\N	\N	\N	2026-09-27 14:14:19.240537+00	\N	1	2026-09-27 14:14:19.240537+00	2026-09-27 14:14:19.240537+00
2c73b3ce-b9b3-447a-97e4-9b591111e6c3	90899efb-4717-4405-b1fd-56715206c652	ba87f661-4299-4fdd-bc69-12f182e3e2dc	APPLIED	ACTIVE	\N	\N	\N	\N	\N	2026-09-27 14:14:19.240537+00	\N	1	2026-09-27 14:14:19.240537+00	2026-09-27 14:14:19.240537+00
\.


--
-- Data for Name: stage_history; Type: TABLE DATA; Schema: crm; Owner: -
--

COPY crm.stage_history (id, application_id, from_stage, to_stage, reason, source, notes, occurred_at, created_at) FROM stdin;
\.


--
-- Data for Name: match_analysis; Type: TABLE DATA; Schema: matching; Owner: -
--

COPY matching.match_analysis (id, assessment_id, cache_key, status, failure_code, detail, summary, strengths, risks, inferences, unknowns, recommended_review, model_id, prompt_version, schema_version, analyzed_at, created_at, total_ms, load_ms, prompt_tokens, prompt_eval_ms, output_tokens, eval_ms, prompt_chars, prompt_tokens_estimate, key_version, payload_hash, payload, inference, context_refs, prompt_budget) FROM stdin;
b7994b11-9e10-4666-83f7-c197d38ed88c	d00c64a4-5a80-4bd5-9667-213cac697f8a	0000000100000001000000010000000100000001000000010000000100000001	AI_COMPLETED	\N	\N	Synthetic fixture analysis 1 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.219436+00	2026-09-27 14:14:08.219436+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
ea384e67-5b18-43a6-8d9b-99605aaffece	b47bea2c-7bfd-4773-9a67-8e215012e621	0000000200000002000000020000000200000002000000020000000200000002	AI_COMPLETED	\N	\N	Synthetic fixture analysis 2 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.226204+00	2026-09-27 14:14:08.226204+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
f4f90ca0-c391-4329-8688-286686ac50ba	9398058c-4b64-4a71-b9aa-35c297548a00	0000000300000003000000030000000300000003000000030000000300000003	AI_COMPLETED	\N	\N	Synthetic fixture analysis 3 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.228834+00	2026-09-27 14:14:08.228834+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
93f8c468-b894-43e9-82dc-c8c950fac534	96f358a4-d14a-4f97-8aea-1f03378184f0	0000000400000004000000040000000400000004000000040000000400000004	AI_COMPLETED	\N	\N	Synthetic fixture analysis 4 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.230273+00	2026-09-27 14:14:08.230273+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
42a4766b-6bd5-46e1-abb7-27c6afbb6663	c08ba0fd-1231-402f-b553-64d53f11a313	0000000500000005000000050000000500000005000000050000000500000005	AI_COMPLETED	\N	\N	Synthetic fixture analysis 5 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.23168+00	2026-09-27 14:14:08.23168+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
bf87c832-c39a-466a-9444-7b89cdb830eb	6f7a3f26-9666-43f6-927b-da84cd895a12	0000000600000006000000060000000600000006000000060000000600000006	AI_COMPLETED	\N	\N	Synthetic fixture analysis 6 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.233153+00	2026-09-27 14:14:08.233153+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
8782f2fd-eceb-451b-9f45-2403f1618d65	0efb175a-b13e-48e8-ae63-f02094b10747	0000000700000007000000070000000700000007000000070000000700000007	AI_COMPLETED	\N	\N	Synthetic fixture analysis 7 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.2346+00	2026-09-27 14:14:08.2346+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
9326674a-777e-44ee-9600-19b11928df35	76d36b0f-d35b-465a-a48f-83ee80e7a6b0	0000000800000008000000080000000800000008000000080000000800000008	AI_COMPLETED	\N	\N	Synthetic fixture analysis 8 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.236097+00	2026-09-27 14:14:08.236097+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
40cabfc5-1a41-4278-9a3c-7c0006b7ea3b	e7cd1de0-1c22-473c-aa57-6fefab179713	0000000900000009000000090000000900000009000000090000000900000009	AI_COMPLETED	\N	\N	Synthetic fixture analysis 9 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.237546+00	2026-09-27 14:14:08.237546+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
2a107433-9802-4977-9a5b-5ba03acd86b4	70c8c450-5949-44b4-8797-9d6dc6e419f5	0000000a0000000a0000000a0000000a0000000a0000000a0000000a0000000a	AI_COMPLETED	\N	\N	Synthetic fixture analysis 10 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.239019+00	2026-09-27 14:14:08.239019+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
a48c5cc1-6519-4a6f-8498-f79e5091c336	c0e980c4-ae73-431c-a15e-0c74d287b53d	0000000b0000000b0000000b0000000b0000000b0000000b0000000b0000000b	AI_COMPLETED	\N	\N	Synthetic fixture analysis 11 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.240639+00	2026-09-27 14:14:08.240639+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
db57c072-5445-4754-8b1e-01e0429dcb40	572e5f57-4c5d-4696-be83-b3a2596a4c3b	0000000c0000000c0000000c0000000c0000000c0000000c0000000c0000000c	AI_COMPLETED	\N	\N	Synthetic fixture analysis 12 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.242244+00	2026-09-27 14:14:08.242244+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
298ccc84-f1a3-4cc6-82de-75d22111f374	eda23bf1-0a47-4007-a7e8-ab621991e9e8	0000000d0000000d0000000d0000000d0000000d0000000d0000000d0000000d	AI_COMPLETED	\N	\N	Synthetic fixture analysis 13 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.243895+00	2026-09-27 14:14:08.243895+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
188b1334-61da-4a13-acfb-e3a85c24d622	73f8e4ca-b23b-4254-8f8e-39b1c3ed652b	0000000e0000000e0000000e0000000e0000000e0000000e0000000e0000000e	AI_COMPLETED	\N	\N	Synthetic fixture analysis 14 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.245457+00	2026-09-27 14:14:08.245457+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
41122c72-b274-4713-b5a6-40dbdbd44ae4	867cd0b0-fd74-4555-8fe3-1aaefa423b1d	0000000f0000000f0000000f0000000f0000000f0000000f0000000f0000000f	AI_COMPLETED	\N	\N	Synthetic fixture analysis 15 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.246895+00	2026-09-27 14:14:08.246895+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
4a4d32ef-922a-47a6-b80a-9713fd94fbe5	3bd9c887-fd23-49a6-8f65-913b44cfa558	0000001000000010000000100000001000000010000000100000001000000010	AI_COMPLETED	\N	\N	Synthetic fixture analysis 16 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.248499+00	2026-09-27 14:14:08.248499+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
9f4d0335-a39d-4557-b0f8-d45995c8f078	ee8628fe-5b7f-496f-abe8-566cd8206ae9	0000001100000011000000110000001100000011000000110000001100000011	AI_COMPLETED	\N	\N	Synthetic fixture analysis 17 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.250096+00	2026-09-27 14:14:08.250096+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
beffc602-bb37-4497-93af-ae54d9201941	50d9b6c9-4a86-4703-b297-6603d52508be	0000001200000012000000120000001200000012000000120000001200000012	AI_COMPLETED	\N	\N	Synthetic fixture analysis 18 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.251552+00	2026-09-27 14:14:08.251552+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
d61da4d2-b365-4b4f-b3ee-576301e21d8c	24c95be8-1b0b-471a-9310-f52d0ccde305	0000001300000013000000130000001300000013000000130000001300000013	AI_COMPLETED	\N	\N	Synthetic fixture analysis 19 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.253286+00	2026-09-27 14:14:08.253286+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
60524695-f0b8-4ae4-8578-54fd3e94cfcc	c51e813b-b69c-487a-948c-d69344868860	0000001400000014000000140000001400000014000000140000001400000014	AI_COMPLETED	\N	\N	Synthetic fixture analysis 20 for F20-48 upgrade proof.	[]	[]	[]	[]	f	qwen3:8b-q4_K_M	v1	v1	2026-09-27 14:14:08.255097+00	2026-09-27 14:14:08.255097+00	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N
\.


--
-- Data for Name: match_analysis_claim; Type: TABLE DATA; Schema: matching; Owner: -
--

COPY matching.match_analysis_claim (assessment_id, owner, claimed_at, expires_at) FROM stdin;
\.


--
-- Data for Name: match_assessment; Type: TABLE DATA; Schema: matching; Owner: -
--

COPY matching.match_assessment (id, opportunity_id, opportunity_version, profile_version_id, input_hash, rules_version, taxonomy_version, opportunity_snapshot, profile_snapshot, eligibility, eligibility_details, status, verdict, score, confidence, assessed_at, created_at) FROM stdin;
d00c64a4-5a80-4bd5-9667-213cac697f8a	e10b2104-35b5-41cf-a57d-50a454944ca4	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	46134ddc6fe658fea72abe4ec8bebde5913ac5830125ca733da913244e4cf7a5	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:e10b2104-35b5-41cf-a57d-50a454944ca4:version:1"], "contract_types": [], "opportunity_id": "e10b2104-35b5-41cf-a57d-50a454944ca4", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:e10b2104-35b5-41cf-a57d-50a454944ca4:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:36.047714+00	2026-09-27 14:13:36.022232+00
b47bea2c-7bfd-4773-9a67-8e215012e621	5bb0d07c-99fa-447a-a6db-7ef00385ef86	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	ed5fa3ea071cf66f5180003677c3aae9fdd059a875aca6840d77ee339788a42b	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:5bb0d07c-99fa-447a-a6db-7ef00385ef86:version:1"], "contract_types": [], "opportunity_id": "5bb0d07c-99fa-447a-a6db-7ef00385ef86", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:5bb0d07c-99fa-447a-a6db-7ef00385ef86:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:36.208903+00	2026-09-27 14:13:36.193857+00
9398058c-4b64-4a71-b9aa-35c297548a00	9cde205b-712f-4f03-800f-c6445ad0a6eb	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	4d51f21f90cddef320ebbb122273b2a352e40b071cff77da2cff039d9cbbce9b	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:9cde205b-712f-4f03-800f-c6445ad0a6eb:version:1"], "contract_types": [], "opportunity_id": "9cde205b-712f-4f03-800f-c6445ad0a6eb", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:9cde205b-712f-4f03-800f-c6445ad0a6eb:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:36.26187+00	2026-09-27 14:13:36.249383+00
96f358a4-d14a-4f97-8aea-1f03378184f0	b06fb893-8eab-43aa-8a5c-75166ca22149	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	65095aa0c5217110b569a56408e5f058c869764a1dc96135e5f494065288fc06	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:b06fb893-8eab-43aa-8a5c-75166ca22149:version:1"], "contract_types": [], "opportunity_id": "b06fb893-8eab-43aa-8a5c-75166ca22149", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:b06fb893-8eab-43aa-8a5c-75166ca22149:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:36.312058+00	2026-09-27 14:13:36.299948+00
c08ba0fd-1231-402f-b553-64d53f11a313	ff7083e5-4ce4-47a9-9860-f1f3f76196f8	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	3e466cfdd4aa40950329f2de06e59c7d2d4f337d381b85c806fbc7d3e2233b99	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:ff7083e5-4ce4-47a9-9860-f1f3f76196f8:version:1"], "contract_types": [], "opportunity_id": "ff7083e5-4ce4-47a9-9860-f1f3f76196f8", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:ff7083e5-4ce4-47a9-9860-f1f3f76196f8:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:36.361313+00	2026-09-27 14:13:36.349401+00
6f7a3f26-9666-43f6-927b-da84cd895a12	250947ce-2088-40f9-b6c3-d0b862f77c4b	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	f8acef84e86a58b479b007484107dba2c33080b4204cc00ca31c13ff874fc9b0	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:250947ce-2088-40f9-b6c3-d0b862f77c4b:version:1"], "contract_types": [], "opportunity_id": "250947ce-2088-40f9-b6c3-d0b862f77c4b", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:250947ce-2088-40f9-b6c3-d0b862f77c4b:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:36.41194+00	2026-09-27 14:13:36.399449+00
0efb175a-b13e-48e8-ae63-f02094b10747	2be0d9b6-4548-47c7-aceb-94d620276fb4	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	4a631d80e475e1dca8ce089de1524fe9a61bc87e043a081da2d2e221597d6512	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:2be0d9b6-4548-47c7-aceb-94d620276fb4:version:1"], "contract_types": [], "opportunity_id": "2be0d9b6-4548-47c7-aceb-94d620276fb4", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:2be0d9b6-4548-47c7-aceb-94d620276fb4:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:36.461472+00	2026-09-27 14:13:36.449272+00
76d36b0f-d35b-465a-a48f-83ee80e7a6b0	08224078-8512-4a17-9cbe-02659abb108a	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	165f4b82e70b83b9236c0baba3572e00bb375d8ad9e5976ac37ed7109ee52b08	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:08224078-8512-4a17-9cbe-02659abb108a:version:1"], "contract_types": [], "opportunity_id": "08224078-8512-4a17-9cbe-02659abb108a", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:08224078-8512-4a17-9cbe-02659abb108a:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:36.511146+00	2026-09-27 14:13:36.498963+00
e7cd1de0-1c22-473c-aa57-6fefab179713	3c4f5629-114a-41b5-b8f4-40615d03dc63	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	9dbb776f00cfcdd9b2fa67977562165bbf7f7bece9ee838cc5b5f84f1ce26f4d	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:3c4f5629-114a-41b5-b8f4-40615d03dc63:version:1"], "contract_types": [], "opportunity_id": "3c4f5629-114a-41b5-b8f4-40615d03dc63", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:3c4f5629-114a-41b5-b8f4-40615d03dc63:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:36.559737+00	2026-09-27 14:13:36.547606+00
70c8c450-5949-44b4-8797-9d6dc6e419f5	70cd12cc-58ca-41b0-9e2b-e0854711afae	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	93d5e04980019f561aae38d530f51c6316a1d4881c59e698fcc1bb77bab66871	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:70cd12cc-58ca-41b0-9e2b-e0854711afae:version:1"], "contract_types": [], "opportunity_id": "70cd12cc-58ca-41b0-9e2b-e0854711afae", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:70cd12cc-58ca-41b0-9e2b-e0854711afae:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:36.609925+00	2026-09-27 14:13:36.597993+00
c0e980c4-ae73-431c-a15e-0c74d287b53d	b14215c9-2d59-4a44-b1a9-34bfb26f2381	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	e70aba2e95a79b2b54ad3939571ba05fdaf8a9303515b6521d4e89e8e1af6406	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:b14215c9-2d59-4a44-b1a9-34bfb26f2381:version:1"], "contract_types": [], "opportunity_id": "b14215c9-2d59-4a44-b1a9-34bfb26f2381", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:b14215c9-2d59-4a44-b1a9-34bfb26f2381:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:36.660171+00	2026-09-27 14:13:36.647968+00
572e5f57-4c5d-4696-be83-b3a2596a4c3b	ce3258fe-4210-4da6-9125-e7220435fed0	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	27a36727f6dd60871dba42440b2b0a00fa9967aecb2052e33c5c0510fd5dcd0f	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:ce3258fe-4210-4da6-9125-e7220435fed0:version:1"], "contract_types": [], "opportunity_id": "ce3258fe-4210-4da6-9125-e7220435fed0", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:ce3258fe-4210-4da6-9125-e7220435fed0:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:36.713573+00	2026-09-27 14:13:36.701062+00
eda23bf1-0a47-4007-a7e8-ab621991e9e8	9dda9b23-9578-475e-9acc-e1df926d3b43	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	6986f14a199cef94db4ae65eeba7b80f436630122c6a3e65a1324512aef83fe2	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:9dda9b23-9578-475e-9acc-e1df926d3b43:version:1"], "contract_types": [], "opportunity_id": "9dda9b23-9578-475e-9acc-e1df926d3b43", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:9dda9b23-9578-475e-9acc-e1df926d3b43:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:36.772667+00	2026-09-27 14:13:36.759599+00
73f8e4ca-b23b-4254-8f8e-39b1c3ed652b	153df84e-624a-4856-83aa-0004a6ebfd6d	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	cc78cc21e9141b7217799f68ec27cf2d768b9509472fb81d3bd2a36f4195f27b	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:153df84e-624a-4856-83aa-0004a6ebfd6d:version:1"], "contract_types": [], "opportunity_id": "153df84e-624a-4856-83aa-0004a6ebfd6d", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:153df84e-624a-4856-83aa-0004a6ebfd6d:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:36.826581+00	2026-09-27 14:13:36.814023+00
867cd0b0-fd74-4555-8fe3-1aaefa423b1d	3f2a8e86-3098-4a3d-9d57-b8d9bfcb7bc1	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	3430c33af9f7945811babb4bc6df4bf13a4c306e4d65e8e214c660e3d0e13d12	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:3f2a8e86-3098-4a3d-9d57-b8d9bfcb7bc1:version:1"], "contract_types": [], "opportunity_id": "3f2a8e86-3098-4a3d-9d57-b8d9bfcb7bc1", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:3f2a8e86-3098-4a3d-9d57-b8d9bfcb7bc1:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:36.879555+00	2026-09-27 14:13:36.867314+00
3bd9c887-fd23-49a6-8f65-913b44cfa558	8be53612-77cc-4a96-b3c1-3c281a5f5e1b	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	f9fce70ad06a29b78b712d5cd69d23ee0acfef8812dfe17936ea92505300862a	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:8be53612-77cc-4a96-b3c1-3c281a5f5e1b:version:1"], "contract_types": [], "opportunity_id": "8be53612-77cc-4a96-b3c1-3c281a5f5e1b", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:8be53612-77cc-4a96-b3c1-3c281a5f5e1b:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:36.933228+00	2026-09-27 14:13:36.921001+00
ee8628fe-5b7f-496f-abe8-566cd8206ae9	ce6090b9-0047-4163-bda3-e30c584ca2a6	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	f437dc83130ca9c8573280c5157c60eaaf71a916c29d4baafcdb2c973a003538	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:ce6090b9-0047-4163-bda3-e30c584ca2a6:version:1"], "contract_types": [], "opportunity_id": "ce6090b9-0047-4163-bda3-e30c584ca2a6", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:ce6090b9-0047-4163-bda3-e30c584ca2a6:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:36.994724+00	2026-09-27 14:13:36.980983+00
50d9b6c9-4a86-4703-b297-6603d52508be	90899efb-4717-4405-b1fd-56715206c652	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	5ca66d31870fb5759cfa5b21e7bf46e34a12880ddc88ef609f4c52e9d1371c5c	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:90899efb-4717-4405-b1fd-56715206c652:version:1"], "contract_types": [], "opportunity_id": "90899efb-4717-4405-b1fd-56715206c652", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:90899efb-4717-4405-b1fd-56715206c652:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:37.04573+00	2026-09-27 14:13:37.033996+00
24c95be8-1b0b-471a-9310-f52d0ccde305	19f8b07d-e01e-4034-bee9-a3b50cdfbca9	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	ecfbf1f57df3b1769aa9e8e9015ebcc8c124ffffc013e2a29b49604caaa4680f	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:19f8b07d-e01e-4034-bee9-a3b50cdfbca9:version:1"], "contract_types": [], "opportunity_id": "19f8b07d-e01e-4034-bee9-a3b50cdfbca9", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:19f8b07d-e01e-4034-bee9-a3b50cdfbca9:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:37.09835+00	2026-09-27 14:13:37.08592+00
c51e813b-b69c-487a-948c-d69344868860	bee90be5-75fe-427d-8d6d-e8e6e47a327c	1	ba87f661-4299-4fdd-bc69-12f182e3e2dc	61836babb75d99c2bdb7683b8b37762b66a1ee8d05371cebaa282c42095c753f	matching-v1	skills-v3	{"status": "DISCOVERED", "seniority": "UNKNOWN", "work_mode": "UNKNOWN", "compensation": null, "published_at": null, "evidence_refs": ["opportunity:bee90be5-75fe-427d-8d6d-e8e6e47a327c:version:1"], "contract_types": [], "opportunity_id": "bee90be5-75fe-427d-8d6d-e8e6e47a327c", "content_version": 1, "required_skills": [], "company_priority": null, "preferred_skills": [], "allowed_countries": [], "work_authorization": "NOT_STATED", "skill_evidence_refs": [], "compensation_conflict": false, "timezone_overlap_hours": null, "compensation_candidates": [], "required_timezone_overlap_hours": null}	{"skills": ["python", "sql"], "countries": ["BR"], "compensation": null, "evidence_refs": ["profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"], "profile_version_id": "ba87f661-4299-4fdd-bc69-12f182e3e2dc", "work_authorization": "UNKNOWN", "accepted_work_modes": ["REMOTE"], "accepted_seniorities": [], "accepted_contract_types": []}	UNKNOWN	[{"code": "OPPORTUNITY_ACTIVE", "reason": "Opportunity is active or newly discovered.", "result": "TRUE", "severity": "HARD", "confidence": "1", "evidence_refs": ["opportunity:bee90be5-75fe-427d-8d6d-e8e6e47a327c:version:1"]}, {"code": "WORK_MODE_COMPATIBLE", "reason": "Work-mode compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "COUNTRY_ALLOWED", "reason": "Residence eligibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "WORK_AUTHORIZATION_COMPATIBLE", "reason": "Work-authorization requirements are not stated conclusively.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "TIMEZONE_COMPATIBLE", "reason": "Required timezone overlap is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "SENIORITY_COMPATIBLE", "reason": "Seniority compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}, {"code": "CONTRACT_COMPATIBLE", "reason": "Contract compatibility is not stated.", "result": "UNKNOWN", "severity": "HARD", "confidence": "0", "evidence_refs": []}]	COMPLETED	REVIEW_REQUIRED	50.0000	0.000	2026-09-27 14:13:37.152189+00	2026-09-27 14:13:37.139475+00
\.


--
-- Data for Name: match_factor; Type: TABLE DATA; Schema: matching; Owner: -
--

COPY matching.match_factor (id, assessment_id, factor_code, weight, raw_score, contribution, status, confidence, missing_policy, explanation, evidence_refs, created_at) FROM stdin;
92175212-3207-406d-a96e-3d21542c11cc	d00c64a4-5a80-4bd5-9667-213cac697f8a	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:e10b2104-35b5-41cf-a57d-50a454944ca4:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:36.022232+00
e6f9212b-eb5b-4e9b-aed0-091f96a13b3d	d00c64a4-5a80-4bd5-9667-213cac697f8a	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:36.022232+00
0cfe0d75-f4c9-4a71-8ecf-be4fc37e99ca	d00c64a4-5a80-4bd5-9667-213cac697f8a	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:36.022232+00
082f4800-79e9-4cae-87dd-cf6504c07ecb	d00c64a4-5a80-4bd5-9667-213cac697f8a	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:36.022232+00
d7357718-a160-44f3-86ee-38e241f3a0b7	d00c64a4-5a80-4bd5-9667-213cac697f8a	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:36.022232+00
fd7e6652-c3b7-4455-bf0a-82ca31282232	d00c64a4-5a80-4bd5-9667-213cac697f8a	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:36.022232+00
f5907678-75e5-446b-a7ef-14769b009e7a	d00c64a4-5a80-4bd5-9667-213cac697f8a	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:36.022232+00
c069eb33-1a81-44f5-b772-3dfea74b15b7	d00c64a4-5a80-4bd5-9667-213cac697f8a	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:36.022232+00
3de8bf54-6316-4a3a-9041-db7b7c914448	b47bea2c-7bfd-4773-9a67-8e215012e621	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:5bb0d07c-99fa-447a-a6db-7ef00385ef86:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:36.193857+00
b96bd817-bf9f-49d3-b463-01d593497e6d	b47bea2c-7bfd-4773-9a67-8e215012e621	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:36.193857+00
113c4fe3-475d-4838-b4db-289ef0f75113	b47bea2c-7bfd-4773-9a67-8e215012e621	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:36.193857+00
7df67d9b-01d7-449a-b963-c7423a0fb189	b47bea2c-7bfd-4773-9a67-8e215012e621	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:36.193857+00
8798544a-49f1-44cc-bc49-3da02682f66b	b47bea2c-7bfd-4773-9a67-8e215012e621	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:36.193857+00
b1c71529-ce2b-41e1-95a4-33ee31fc60cd	b47bea2c-7bfd-4773-9a67-8e215012e621	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:36.193857+00
08040db4-9afc-40df-adaa-5be9732e5c7e	b47bea2c-7bfd-4773-9a67-8e215012e621	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:36.193857+00
b9762195-208d-465d-a337-6427d945814a	b47bea2c-7bfd-4773-9a67-8e215012e621	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:36.193857+00
e252ffd8-36e0-4fe3-8291-4e129b2653f3	9398058c-4b64-4a71-b9aa-35c297548a00	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:9cde205b-712f-4f03-800f-c6445ad0a6eb:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:36.249383+00
16e6054a-e026-43e9-be58-51d7d35fc4c5	9398058c-4b64-4a71-b9aa-35c297548a00	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:36.249383+00
61e08e3c-d164-4aa3-b0fd-e540c69b7629	9398058c-4b64-4a71-b9aa-35c297548a00	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:36.249383+00
ea3705c3-7d50-4ae3-9900-619f061e4daf	9398058c-4b64-4a71-b9aa-35c297548a00	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:36.249383+00
f235879e-b607-4f41-99fb-77bef3dc0898	9398058c-4b64-4a71-b9aa-35c297548a00	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:36.249383+00
f03f63c0-9f77-454a-9b80-f77d96f07c57	9398058c-4b64-4a71-b9aa-35c297548a00	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:36.249383+00
7cbb4393-8806-40fd-ac14-25d75d4f68f5	9398058c-4b64-4a71-b9aa-35c297548a00	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:36.249383+00
efad9f64-5d8f-4a86-970a-ed6ce64c3874	9398058c-4b64-4a71-b9aa-35c297548a00	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:36.249383+00
6b2a2bd6-2442-47f3-9d7c-106ff610746f	96f358a4-d14a-4f97-8aea-1f03378184f0	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:b06fb893-8eab-43aa-8a5c-75166ca22149:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:36.299948+00
01709c91-9901-4230-95e8-7ddfc2434d29	96f358a4-d14a-4f97-8aea-1f03378184f0	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:36.299948+00
6d6bf5fe-6c52-4637-88cc-0bbb52e2f2d0	96f358a4-d14a-4f97-8aea-1f03378184f0	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:36.299948+00
e6afefd1-91e8-4c7a-8d0e-9f7e5d98a76f	96f358a4-d14a-4f97-8aea-1f03378184f0	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:36.299948+00
7c6edbc1-21f0-4cf4-a57e-f3197dc37163	96f358a4-d14a-4f97-8aea-1f03378184f0	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:36.299948+00
1b556122-e69b-4616-9c6b-1c4ab862bd05	96f358a4-d14a-4f97-8aea-1f03378184f0	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:36.299948+00
8dcb8f14-168c-4618-9d9c-cc376547ae60	96f358a4-d14a-4f97-8aea-1f03378184f0	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:36.299948+00
89d5cb93-7de1-41cd-8fa8-6c73ffe5c76b	96f358a4-d14a-4f97-8aea-1f03378184f0	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:36.299948+00
67c8675a-dbb7-4368-8c9b-5e7902f8c3b6	c08ba0fd-1231-402f-b553-64d53f11a313	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:ff7083e5-4ce4-47a9-9860-f1f3f76196f8:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:36.349401+00
2b012f4d-6012-4b79-9139-f81e6d394997	c08ba0fd-1231-402f-b553-64d53f11a313	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:36.349401+00
dbf12ffd-63de-41c1-9904-873dffd17606	c08ba0fd-1231-402f-b553-64d53f11a313	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:36.349401+00
b6768946-674e-4069-98ef-41f1e049c477	c08ba0fd-1231-402f-b553-64d53f11a313	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:36.349401+00
89ad7b44-fdff-44e2-8284-6ec827b8f415	c08ba0fd-1231-402f-b553-64d53f11a313	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:36.349401+00
e89e3649-d4e5-4d36-ba07-8fc5588f0613	c08ba0fd-1231-402f-b553-64d53f11a313	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:36.349401+00
b99d23c3-aa85-469b-9c2b-0ce52bc2b91d	c08ba0fd-1231-402f-b553-64d53f11a313	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:36.349401+00
51bbe144-7bcb-4da2-b2a0-05c82cc312f5	c08ba0fd-1231-402f-b553-64d53f11a313	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:36.349401+00
14cd7f86-0ddf-4f0b-b649-6fdc53d9f872	6f7a3f26-9666-43f6-927b-da84cd895a12	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:250947ce-2088-40f9-b6c3-d0b862f77c4b:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:36.399449+00
dd3899da-b08d-467c-a73a-3844e85eb950	6f7a3f26-9666-43f6-927b-da84cd895a12	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:36.399449+00
9910a47f-ec09-4e16-a063-b33bd701cb53	6f7a3f26-9666-43f6-927b-da84cd895a12	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:36.399449+00
d95575b3-451d-4162-9c8e-ea6ddef04152	6f7a3f26-9666-43f6-927b-da84cd895a12	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:36.399449+00
edb4ea70-10aa-46d5-84ce-8362d433ca56	6f7a3f26-9666-43f6-927b-da84cd895a12	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:36.399449+00
09a4849e-79be-4990-9281-cdff79ec319a	6f7a3f26-9666-43f6-927b-da84cd895a12	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:36.399449+00
0ff4f4da-d630-4f76-ad55-b4fd24055788	6f7a3f26-9666-43f6-927b-da84cd895a12	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:36.399449+00
7a57d051-c2ad-4322-bbc9-6b808b60c829	6f7a3f26-9666-43f6-927b-da84cd895a12	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:36.399449+00
9a77c6ee-1d9c-4d38-959c-74440b128345	0efb175a-b13e-48e8-ae63-f02094b10747	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:2be0d9b6-4548-47c7-aceb-94d620276fb4:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:36.449272+00
01b72eea-8cd1-417a-8c28-38f0b638c040	0efb175a-b13e-48e8-ae63-f02094b10747	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:36.449272+00
a1e264f3-80cf-4cb6-b976-16075e755b6b	0efb175a-b13e-48e8-ae63-f02094b10747	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:36.449272+00
3305c39c-3df5-43ae-94da-b1a104467601	0efb175a-b13e-48e8-ae63-f02094b10747	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:36.449272+00
18ab2a59-33e8-4d4a-86f0-d868f043b019	0efb175a-b13e-48e8-ae63-f02094b10747	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:36.449272+00
98d9cde9-a1e3-426f-9088-765481aa66f3	0efb175a-b13e-48e8-ae63-f02094b10747	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:36.449272+00
34e25dfb-17bb-41ba-9b87-ee98c1253ed8	0efb175a-b13e-48e8-ae63-f02094b10747	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:36.449272+00
7613c8df-565d-44fc-b9fe-6345c10f82bc	0efb175a-b13e-48e8-ae63-f02094b10747	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:36.449272+00
b6d027ea-df72-401b-8ac9-bb6af6dfebda	76d36b0f-d35b-465a-a48f-83ee80e7a6b0	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:08224078-8512-4a17-9cbe-02659abb108a:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:36.498963+00
46392daf-5bd6-4663-a53a-e911f616229a	76d36b0f-d35b-465a-a48f-83ee80e7a6b0	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:36.498963+00
a223375d-8c65-4783-a086-ace79f845f34	76d36b0f-d35b-465a-a48f-83ee80e7a6b0	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:36.498963+00
869afe9a-ba06-4ccb-abcb-57fefaa85d71	76d36b0f-d35b-465a-a48f-83ee80e7a6b0	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:36.498963+00
9a5e2e74-fed9-4ee6-aebe-222f49eb2202	76d36b0f-d35b-465a-a48f-83ee80e7a6b0	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:36.498963+00
e9e02f41-7a52-414c-b0c5-52bcffa5c488	76d36b0f-d35b-465a-a48f-83ee80e7a6b0	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:36.498963+00
2c22d580-943c-4c7b-886f-b7105cc2aac1	76d36b0f-d35b-465a-a48f-83ee80e7a6b0	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:36.498963+00
b540599b-324c-4517-85ab-fd25dc541d01	76d36b0f-d35b-465a-a48f-83ee80e7a6b0	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:36.498963+00
5f02d660-9520-41db-bb9a-9d39b0df5892	e7cd1de0-1c22-473c-aa57-6fefab179713	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:3c4f5629-114a-41b5-b8f4-40615d03dc63:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:36.547606+00
31ef3061-a27e-4640-b74c-782dcb793c5b	e7cd1de0-1c22-473c-aa57-6fefab179713	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:36.547606+00
54db91db-810c-4d6b-b359-be868596eef6	e7cd1de0-1c22-473c-aa57-6fefab179713	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:36.547606+00
489b6750-a9d6-4c15-9787-1b18788d4c08	e7cd1de0-1c22-473c-aa57-6fefab179713	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:36.547606+00
7409d5cc-ceb1-40e8-80c6-48e80cdc4f60	e7cd1de0-1c22-473c-aa57-6fefab179713	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:36.547606+00
ef30c298-f6cd-4d20-824c-a57f8b9c3544	e7cd1de0-1c22-473c-aa57-6fefab179713	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:36.547606+00
3a9764bf-3efe-4ce6-a63e-6a80925ed918	e7cd1de0-1c22-473c-aa57-6fefab179713	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:36.547606+00
c5e2b821-4b91-48ca-a616-943362f2865c	e7cd1de0-1c22-473c-aa57-6fefab179713	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:36.547606+00
3edbbdef-6f2e-44bd-9758-7f7d783326cf	70c8c450-5949-44b4-8797-9d6dc6e419f5	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:70cd12cc-58ca-41b0-9e2b-e0854711afae:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:36.597993+00
5cac1a8f-5268-40d3-a9bd-0f39d784a8f8	70c8c450-5949-44b4-8797-9d6dc6e419f5	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:36.597993+00
02661568-8a56-4727-8547-b5c87d5f8b9d	70c8c450-5949-44b4-8797-9d6dc6e419f5	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:36.597993+00
ca0d61e9-f20c-4fa4-9a51-04fb48c97fb8	70c8c450-5949-44b4-8797-9d6dc6e419f5	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:36.597993+00
08de282f-0235-4b23-a50a-18490a03c130	70c8c450-5949-44b4-8797-9d6dc6e419f5	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:36.597993+00
5f651a84-31ae-420a-8e09-f3c8a9d25380	70c8c450-5949-44b4-8797-9d6dc6e419f5	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:36.597993+00
1f2b2b10-3f24-4afe-b573-53129bb752d6	70c8c450-5949-44b4-8797-9d6dc6e419f5	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:36.597993+00
bcf43200-f82f-4904-91a3-365943b5f4ca	70c8c450-5949-44b4-8797-9d6dc6e419f5	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:36.597993+00
af5c4958-f0eb-4c3c-9d65-55d4dd5327d2	c0e980c4-ae73-431c-a15e-0c74d287b53d	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:b14215c9-2d59-4a44-b1a9-34bfb26f2381:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:36.647968+00
60075cca-254c-46d8-8b3d-f58d60edd643	c0e980c4-ae73-431c-a15e-0c74d287b53d	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:36.647968+00
ace02ec0-d91d-44b8-bd92-a497a75ea49f	c0e980c4-ae73-431c-a15e-0c74d287b53d	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:36.647968+00
ee700863-d552-431c-ae95-a6d1d5d35c5e	c0e980c4-ae73-431c-a15e-0c74d287b53d	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:36.647968+00
41a34b39-e5a6-4045-a8a8-ee855e64774a	c0e980c4-ae73-431c-a15e-0c74d287b53d	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:36.647968+00
b7974e1c-b741-4b85-93a7-99cc5fa73eff	c0e980c4-ae73-431c-a15e-0c74d287b53d	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:36.647968+00
7adbab66-f541-4802-a9a9-406ef1786c5a	c0e980c4-ae73-431c-a15e-0c74d287b53d	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:36.647968+00
35c6c1e3-df44-4282-b633-7fac6099d2db	c0e980c4-ae73-431c-a15e-0c74d287b53d	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:36.647968+00
cd4d6ea6-36b8-435c-8954-688580e5e75e	572e5f57-4c5d-4696-be83-b3a2596a4c3b	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:ce3258fe-4210-4da6-9125-e7220435fed0:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:36.701062+00
de86c550-be8d-40ac-965b-f69a771635d1	572e5f57-4c5d-4696-be83-b3a2596a4c3b	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:36.701062+00
316530ae-8d29-44f2-9f5e-dfdd0daa2159	572e5f57-4c5d-4696-be83-b3a2596a4c3b	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:36.701062+00
6281414d-0ab1-4c51-849e-5d6c97f43617	572e5f57-4c5d-4696-be83-b3a2596a4c3b	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:36.701062+00
485c6fca-ab8b-48c1-a7f4-8e7765fdf87a	572e5f57-4c5d-4696-be83-b3a2596a4c3b	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:36.701062+00
7174f49d-3f77-4d3b-b7cb-07423a71c5aa	572e5f57-4c5d-4696-be83-b3a2596a4c3b	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:36.701062+00
7f8ba58b-72cf-4624-a49d-62f493fa9f28	572e5f57-4c5d-4696-be83-b3a2596a4c3b	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:36.701062+00
da12c12e-34f5-4055-985b-d8017cc4a710	572e5f57-4c5d-4696-be83-b3a2596a4c3b	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:36.701062+00
54656b1e-4e69-4c53-ad52-6cff90fb614e	eda23bf1-0a47-4007-a7e8-ab621991e9e8	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:9dda9b23-9578-475e-9acc-e1df926d3b43:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:36.759599+00
81a8e8c4-9772-4b8e-bc6d-a11a87a78482	eda23bf1-0a47-4007-a7e8-ab621991e9e8	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:36.759599+00
98e031dd-996f-483f-bcca-33436d1841f7	eda23bf1-0a47-4007-a7e8-ab621991e9e8	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:36.759599+00
c5d3dc9b-98a4-4147-b744-9e71765e4301	eda23bf1-0a47-4007-a7e8-ab621991e9e8	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:36.759599+00
4d394443-182e-496b-9d03-4c775e008e0f	eda23bf1-0a47-4007-a7e8-ab621991e9e8	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:36.759599+00
aff0d162-0b22-4726-864b-4eb6fbb95a5d	eda23bf1-0a47-4007-a7e8-ab621991e9e8	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:36.759599+00
fda0f3cb-1554-4096-a60b-af6548af7b7b	eda23bf1-0a47-4007-a7e8-ab621991e9e8	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:36.759599+00
953ef9e8-eb1d-4bfc-a11c-dff923428579	eda23bf1-0a47-4007-a7e8-ab621991e9e8	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:36.759599+00
a0ea3882-590f-4aca-b8c1-dac82b497942	73f8e4ca-b23b-4254-8f8e-39b1c3ed652b	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:153df84e-624a-4856-83aa-0004a6ebfd6d:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:36.814023+00
21f0dd21-9942-4645-bace-901eda9d1f18	73f8e4ca-b23b-4254-8f8e-39b1c3ed652b	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:36.814023+00
8f3509f4-0943-484b-a876-8d7e378c4cdb	73f8e4ca-b23b-4254-8f8e-39b1c3ed652b	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:36.814023+00
a854dea1-3e1b-44a7-b6bb-0cd121aa1e35	73f8e4ca-b23b-4254-8f8e-39b1c3ed652b	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:36.814023+00
d61ded3c-14ad-41c3-ac18-bfdba756add2	73f8e4ca-b23b-4254-8f8e-39b1c3ed652b	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:36.814023+00
adb9b8a8-6dfc-4174-a8b0-62153f39b326	73f8e4ca-b23b-4254-8f8e-39b1c3ed652b	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:36.814023+00
b4c089f2-d8ab-4d2c-9b8c-11645f53cb23	73f8e4ca-b23b-4254-8f8e-39b1c3ed652b	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:36.814023+00
94c5444e-cb6f-4a26-8b90-cf8835b1bb91	73f8e4ca-b23b-4254-8f8e-39b1c3ed652b	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:36.814023+00
7c931bf3-e937-4382-854d-65d6f7ef2856	867cd0b0-fd74-4555-8fe3-1aaefa423b1d	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:3f2a8e86-3098-4a3d-9d57-b8d9bfcb7bc1:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:36.867314+00
8b350d70-e37d-489f-8a09-5d23b6ec83f7	867cd0b0-fd74-4555-8fe3-1aaefa423b1d	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:36.867314+00
353c3a8b-27ee-4226-b936-0f6bb14061bc	867cd0b0-fd74-4555-8fe3-1aaefa423b1d	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:36.867314+00
27a9695a-73be-44d5-a9e6-a67c1512e0c9	867cd0b0-fd74-4555-8fe3-1aaefa423b1d	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:36.867314+00
902d793f-4f5b-4a31-8f3a-4bc26110621f	867cd0b0-fd74-4555-8fe3-1aaefa423b1d	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:36.867314+00
bb61c406-6a3c-4b69-a0cd-b927c16259c0	867cd0b0-fd74-4555-8fe3-1aaefa423b1d	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:36.867314+00
e063ebf6-6239-4110-980e-01ce6dd0a454	867cd0b0-fd74-4555-8fe3-1aaefa423b1d	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:36.867314+00
51dc9b50-6f34-4570-9e45-0cf3b5f72f6e	867cd0b0-fd74-4555-8fe3-1aaefa423b1d	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:36.867314+00
567ade1a-46b1-4a29-b442-fb552074126f	3bd9c887-fd23-49a6-8f65-913b44cfa558	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:8be53612-77cc-4a96-b3c1-3c281a5f5e1b:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:36.921001+00
0f959832-27a0-45be-a23e-c50327033057	3bd9c887-fd23-49a6-8f65-913b44cfa558	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:36.921001+00
eb16ec29-52af-431a-bc18-2fbaaf1bd0ee	3bd9c887-fd23-49a6-8f65-913b44cfa558	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:36.921001+00
1c0a3853-d928-4eb2-a198-2e8f6c05a8f2	3bd9c887-fd23-49a6-8f65-913b44cfa558	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:36.921001+00
6679a765-bf60-403e-b92f-8e07dc6b525f	3bd9c887-fd23-49a6-8f65-913b44cfa558	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:36.921001+00
72e2a1c5-82d1-400b-a2f6-ce4707a75cae	3bd9c887-fd23-49a6-8f65-913b44cfa558	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:36.921001+00
625231b0-139e-412d-8139-b56875f1b127	3bd9c887-fd23-49a6-8f65-913b44cfa558	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:36.921001+00
13de3cae-245b-4364-bbf7-a79c6540495a	3bd9c887-fd23-49a6-8f65-913b44cfa558	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:36.921001+00
a09866d8-2bdb-47a1-9afa-fae656d86288	ee8628fe-5b7f-496f-abe8-566cd8206ae9	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:ce6090b9-0047-4163-bda3-e30c584ca2a6:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:36.980983+00
50306bb5-342e-4daf-9dce-de5f8f61f897	ee8628fe-5b7f-496f-abe8-566cd8206ae9	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:36.980983+00
1ecaa4b2-0df9-4a5a-834b-03f0be4c9495	ee8628fe-5b7f-496f-abe8-566cd8206ae9	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:36.980983+00
876c7857-89cb-4709-87c8-89320bbf7b78	ee8628fe-5b7f-496f-abe8-566cd8206ae9	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:36.980983+00
fe2344a8-792a-473f-ba1f-ca24229d2eaf	ee8628fe-5b7f-496f-abe8-566cd8206ae9	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:36.980983+00
a9d1daf9-405f-4d2a-9932-2557707cbc7a	ee8628fe-5b7f-496f-abe8-566cd8206ae9	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:36.980983+00
011ec6e7-6ead-4864-8d5c-f1a8666e20ad	ee8628fe-5b7f-496f-abe8-566cd8206ae9	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:36.980983+00
fb76cfc7-4b4e-4903-8555-aa4b51c106d7	ee8628fe-5b7f-496f-abe8-566cd8206ae9	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:36.980983+00
7e65e0f9-f828-44d8-9160-81431c0795d1	50d9b6c9-4a86-4703-b297-6603d52508be	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:90899efb-4717-4405-b1fd-56715206c652:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:37.033996+00
1dfd4e59-4949-4542-82c6-7d3a191e15e3	50d9b6c9-4a86-4703-b297-6603d52508be	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:37.033996+00
d8f51a3c-4678-41fb-9919-26826225073c	50d9b6c9-4a86-4703-b297-6603d52508be	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:37.033996+00
f6b0df61-e168-4d42-83b2-4e76128c5e3b	50d9b6c9-4a86-4703-b297-6603d52508be	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:37.033996+00
32fae4f5-a49c-4c21-907e-1a4062b19ab5	50d9b6c9-4a86-4703-b297-6603d52508be	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:37.033996+00
3d384984-566e-4383-911b-b06f6c7bcc38	50d9b6c9-4a86-4703-b297-6603d52508be	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:37.033996+00
d55b6e35-a396-4fe3-8f0c-dba52ce6b8e9	50d9b6c9-4a86-4703-b297-6603d52508be	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:37.033996+00
3498deca-0443-4a5c-b4af-35951d274482	50d9b6c9-4a86-4703-b297-6603d52508be	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:37.033996+00
b5dd3b20-04bf-4236-994d-96c5fb7be0a5	24c95be8-1b0b-471a-9310-f52d0ccde305	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:19f8b07d-e01e-4034-bee9-a3b50cdfbca9:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:37.08592+00
a8213dbf-cd3c-4577-b076-1914ac69e762	24c95be8-1b0b-471a-9310-f52d0ccde305	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:37.08592+00
16c7d8f3-6bbd-4360-bfb2-30dd50e6ecc6	24c95be8-1b0b-471a-9310-f52d0ccde305	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:37.08592+00
371792b4-0cca-4fc7-a533-3c7efbdc3c61	24c95be8-1b0b-471a-9310-f52d0ccde305	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:37.08592+00
b8693942-9167-4906-8fc7-81d76bb4bc42	24c95be8-1b0b-471a-9310-f52d0ccde305	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:37.08592+00
318c42c3-4803-44ec-97cd-ed6ac98f1a60	24c95be8-1b0b-471a-9310-f52d0ccde305	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:37.08592+00
b5d1ddf3-be35-43f7-9768-24bda9807852	24c95be8-1b0b-471a-9310-f52d0ccde305	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:37.08592+00
32e9e26c-da7c-4b80-9fb1-0b990e4a49ee	24c95be8-1b0b-471a-9310-f52d0ccde305	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:37.08592+00
c991a820-a726-4077-8efa-1793ba740f04	c51e813b-b69c-487a-948c-d69344868860	GEOGRAPHY_CONTRACT_FIT	0.2000	0.5000	10.0000	UNKNOWN	0.000	REQUIRE_REVIEW	Geography or contract data is incomplete.	["opportunity:bee90be5-75fe-427d-8d6d-e8e6e47a327c:version:1", "profile-version:ba87f661-4299-4fdd-bc69-12f182e3e2dc"]	2026-09-27 14:13:37.139475+00
6344b789-8574-4e98-9bf2-d9c5ce53bf3d	c51e813b-b69c-487a-948c-d69344868860	TECHNOLOGY_FIT	0.2500	0.5000	12.5000	UNKNOWN	0.000	NEUTRAL	Opportunity skills are not classified.	[]	2026-09-27 14:13:37.139475+00
a04db2b5-a472-4fec-b9a8-adf7244a3f4a	c51e813b-b69c-487a-948c-d69344868860	COMPANY_PRIORITY	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	Company priority is not configured.	[]	2026-09-27 14:13:37.139475+00
437f78fe-b46d-434a-ad5e-51f0ec701733	c51e813b-b69c-487a-948c-d69344868860	DOMAIN_EXPERIENCE	0.1500	0.5000	7.5000	UNKNOWN	0.000	NEUTRAL	No normalized evidence is available for this factor.	[]	2026-09-27 14:13:37.139475+00
6fa4e5a8-ff0d-4ce1-89d5-29334c843394	c51e813b-b69c-487a-948c-d69344868860	SENIORITY_SCOPE	0.1000	0.5000	5.0000	UNKNOWN	0.000	NEUTRAL	Seniority compatibility is not stated.	[]	2026-09-27 14:13:37.139475+00
be446578-a7f4-4308-b945-5d2ab8e5926a	c51e813b-b69c-487a-948c-d69344868860	CONTRACT_COMPENSATION	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Contract compatibility is not stated.	[]	2026-09-27 14:13:37.139475+00
522a294c-1008-4ad7-ac8e-61d9d3d03f83	c51e813b-b69c-487a-948c-d69344868860	TIMEZONE	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Required timezone overlap is not stated.	[]	2026-09-27 14:13:37.139475+00
392444aa-4722-4377-a4cb-609de57381be	c51e813b-b69c-487a-948c-d69344868860	RECENCY	0.0500	0.5000	2.5000	UNKNOWN	0.000	NEUTRAL	Publication date or assessment timestamp is unavailable.	[]	2026-09-27 14:13:37.139475+00
\.


--
-- Data for Name: normalization_result; Type: TABLE DATA; Schema: opportunities; Owner: -
--

COPY opportunities.normalization_result (id, raw_item_id, opportunity_id, source_occurrence_id, status, normalizer_version, identity_decision, reasons, error_summary, processed_at) FROM stdin;
b475368d-a919-4e28-8311-3e1952b3d5ca	005a6afe-f63e-4bb8-be0b-5fd2724742ec	bee90be5-75fe-427d-8d6d-e8e6e47a327c	a989ca0e-62f1-47c6-9c94-69d5f9719cd6	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:39.784016+00
c636a4cc-c2f7-43ee-ac43-3faf0e7e5516	19a81372-2092-4385-9b5f-0388cee53e81	19f8b07d-e01e-4034-bee9-a3b50cdfbca9	b560e4d3-1185-4768-9d17-9a4039d3d521	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:39.988195+00
035c6be3-6337-4192-bf07-db72852aa6e5	1c07155c-5c37-44d7-83ff-a4ea4ff9cb48	90899efb-4717-4405-b1fd-56715206c652	240b3b3f-7402-4b22-b1e1-afeb9e64334d	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:40.031062+00
bd170378-1611-4827-a6db-24e54290275e	310610b2-1e99-4e78-bedd-d364383c35f2	ce6090b9-0047-4163-bda3-e30c584ca2a6	d7facc58-1d17-48ee-b64c-8092758f44d6	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:40.067616+00
1b7db7f0-d67c-4db5-8d66-2c704d1c56c6	388fd30a-292b-4128-88f4-c7d808828dfa	8be53612-77cc-4a96-b3c1-3c281a5f5e1b	5c3dedc5-6e21-493c-b950-25919f90c7f8	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:40.100711+00
e6ad49d6-cfcb-4e62-aaac-a77ce5d7fdf0	49b4b3a7-be04-4077-8a3a-634ce5b9cd02	3f2a8e86-3098-4a3d-9d57-b8d9bfcb7bc1	28331fdb-0550-4fb1-96e3-14d08cb35f8c	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:40.136899+00
13f0fe1e-39b1-458c-b602-ade906bc2456	4d7cfa7b-2c02-442b-8339-9361412c006e	153df84e-624a-4856-83aa-0004a6ebfd6d	a97d3b54-6fd8-47fc-9892-68902ee96364	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:40.179302+00
c9879fc2-dc0e-4d2c-b9a0-1546274313fb	818b70a4-9057-4d51-b19c-832c8c2bf892	9dda9b23-9578-475e-9acc-e1df926d3b43	77e3279f-3d01-49b9-925e-15a3367a9036	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:40.211721+00
b1d5b70e-44bb-40e0-bd8e-249ea1574b01	9a2bb19b-7935-4087-84bb-1af773401c4f	ce3258fe-4210-4da6-9125-e7220435fed0	cdf5a757-60e7-47c8-825a-e90af5d6d01f	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:40.241841+00
da037882-0624-4e68-900e-2b513b5bd8a1	ae475ec9-60db-4ba8-a5f5-3ce782d31ba8	b14215c9-2d59-4a44-b1a9-34bfb26f2381	d98eb29a-3e9f-4458-832b-41700b01f2e6	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:40.272773+00
8bcae2f6-bc20-4a90-8bea-114bc425dc2c	b092dfbc-4e40-4399-9f75-c577d698e8b4	70cd12cc-58ca-41b0-9e2b-e0854711afae	db04a940-df97-46f4-b27c-1dda956b13f2	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:40.30338+00
0f90586b-ac50-44ab-afd0-88f1fe2436db	bc90a2a2-91db-4e49-97ab-bf19066397a2	3c4f5629-114a-41b5-b8f4-40615d03dc63	9d89cb60-495a-4dd2-a24c-846c70e27af6	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:40.336627+00
e9d874e4-a67a-4d72-8d85-7e79ac457ce6	c6e2a518-f82e-4a0e-9f10-c9fd035795eb	08224078-8512-4a17-9cbe-02659abb108a	7fd616a1-9b53-4c9b-b5b3-b02e5fec247f	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:40.367358+00
c44884b8-c38d-468e-8e5a-ef42fcca883e	ca12553c-e8ba-4220-ab51-39fd091bdc0d	2be0d9b6-4548-47c7-aceb-94d620276fb4	472373f5-b490-4d54-9c8d-a6233a290cd3	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:40.397452+00
976b5d82-5cdf-46e5-962c-ecf0c312be3f	dfad672c-01cf-49bd-91a7-7c39211e0dfb	250947ce-2088-40f9-b6c3-d0b862f77c4b	b0bddb69-7203-4475-958b-acffa10e0099	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:40.426798+00
662ff9c8-b6ef-4795-bdd7-82c9339c6f21	e169598b-42d5-4267-97fb-ea83d2f49ac8	ff7083e5-4ce4-47a9-9860-f1f3f76196f8	7a1b5117-ed45-4a68-b37e-b99a65d37b77	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:40.46066+00
ed4d14ef-5e4d-4c1c-ba65-f69cd58af30a	e967f036-6280-4f34-b6ff-7befdfc8d318	b06fb893-8eab-43aa-8a5c-75166ca22149	7d6bf222-e712-4870-a9d4-9b1ef2894169	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:40.489952+00
5bedd84d-e892-45e3-9e45-f42ffb2b374d	f129b7e1-36bc-425a-b971-01ade87c32fd	9cde205b-712f-4f03-800f-c6445ad0a6eb	d843975e-4a0f-43f8-bab2-4aa016309227	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:40.517839+00
f459248a-3851-4328-95bb-555edfadbbdb	f33ac04f-b48f-4216-bbd6-5f9bcf539907	5bb0d07c-99fa-447a-a6db-7ef00385ef86	b9e9e2a7-d1fa-4387-8c51-bb2a406a0128	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:40.545721+00
0a3f2054-fcc5-43b9-a479-a8704becfbac	ff51a452-8ba7-434f-b9d6-f1f841726c80	e10b2104-35b5-41cf-a57d-50a454944ca4	cdf79f4b-c37b-4212-b200-dc11b08e7ac0	SUCCEEDED	v5	NEW	[{"code": "NO_IDENTITY_MATCH"}, {"code": "SENIORITY_CLASSIFICATION", "value": "UNKNOWN", "source": "title", "collector": "manual", "external_value": null, "mapping_version": "seniority-v2"}]	\N	2026-09-27 14:12:40.573753+00
\.


--
-- Data for Name: opportunity; Type: TABLE DATA; Schema: opportunities; Owner: -
--

COPY opportunities.opportunity (id, fingerprint, fingerprint_version, canonical_title, normalized_title, canonical_company_id, company_name, normalized_company_name, location_text, normalized_location, work_mode, seniority, contract_type, description, lifecycle_status, published_at, source_updated_at, created_at, updated_at, version, closure_evidence, role_family, role_family_evidence, role_family_version, search_skills, allowed_countries, allowed_countries_version) FROM stdin;
bee90be5-75fe-427d-8d6d-e8e6e47a327c	cb4e421ef44895bfea499f3841dc8ffa9ffc536d46a5b39dd1ca2c4d33467297	v1	Backend Engineer 18	backend engineer 18	\N	Fixture Co 18	fixture co 18	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:39.784016+00	2026-09-27 14:12:39.784016+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
19f8b07d-e01e-4034-bee9-a3b50cdfbca9	4b74ea63e4039f2039e51c3dc6683b931260412aa5d28045dacb915513e9f75a	v1	Backend Engineer 3	backend engineer 3	\N	Fixture Co 3	fixture co 3	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:39.988195+00	2026-09-27 14:12:39.988195+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
90899efb-4717-4405-b1fd-56715206c652	74155a58aa6f44f6b5b4e643c027dc8a1a8bc66c5dd466060ba37c8a834aa435	v1	Backend Engineer 20	backend engineer 20	\N	Fixture Co 20	fixture co 20	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:40.031062+00	2026-09-27 14:12:40.031062+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
ce6090b9-0047-4163-bda3-e30c584ca2a6	d21db407672a8f0203aee23d51785757898a26728f6314a9b70a889079949adf	v1	Backend Engineer 14	backend engineer 14	\N	Fixture Co 14	fixture co 14	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:40.067616+00	2026-09-27 14:12:40.067616+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
8be53612-77cc-4a96-b3c1-3c281a5f5e1b	90db056904500a6329c97a37155330f40533412a04d3aca9d57d2492d5fb9b83	v1	Backend Engineer 2	backend engineer 2	\N	Fixture Co 2	fixture co 2	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:40.100711+00	2026-09-27 14:12:40.100711+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
3f2a8e86-3098-4a3d-9d57-b8d9bfcb7bc1	2fb35ce00d6b3b70cb281156ca2850d215a9509ee24c530819f2dba23034406d	v1	Backend Engineer 19	backend engineer 19	\N	Fixture Co 19	fixture co 19	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:40.136899+00	2026-09-27 14:12:40.136899+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
153df84e-624a-4856-83aa-0004a6ebfd6d	8659b5a1b2a0b1d4d9e1367b7307a9c4fbefa016461631d77eec1dd36af3e773	v1	Backend Engineer 9	backend engineer 9	\N	Fixture Co 9	fixture co 9	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:40.179302+00	2026-09-27 14:12:40.179302+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
9dda9b23-9578-475e-9acc-e1df926d3b43	3d76b0dd22eabb44a68e9e42d239d36bfdeaeaf1ceb899d8e6f27bd26f720af7	v1	Backend Engineer 12	backend engineer 12	\N	Fixture Co 12	fixture co 12	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:40.211721+00	2026-09-27 14:12:40.211721+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
ce3258fe-4210-4da6-9125-e7220435fed0	35dadbf14ed34444c1d5f065dcda9a9ab6f6fc195f30187d273cdece20408e25	v1	Backend Engineer 13	backend engineer 13	\N	Fixture Co 13	fixture co 13	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:40.241841+00	2026-09-27 14:12:40.241841+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
b14215c9-2d59-4a44-b1a9-34bfb26f2381	2a6b1b47f414a64ba3e33d7bf72e16be5468089776bd09efa91959c70c759d10	v1	Backend Engineer 4	backend engineer 4	\N	Fixture Co 4	fixture co 4	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:40.272773+00	2026-09-27 14:12:40.272773+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
70cd12cc-58ca-41b0-9e2b-e0854711afae	2e7332060577acadf9f095facaa1053b3ab356a15692a723fde61e350158cdcc	v1	Backend Engineer 11	backend engineer 11	\N	Fixture Co 11	fixture co 11	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:40.30338+00	2026-09-27 14:12:40.30338+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
3c4f5629-114a-41b5-b8f4-40615d03dc63	1e080d19148a339b9c4aa3af0127fe385f921a1c641d56d7469b6d1a0748a4ad	v1	Backend Engineer 17	backend engineer 17	\N	Fixture Co 17	fixture co 17	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:40.336627+00	2026-09-27 14:12:40.336627+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
08224078-8512-4a17-9cbe-02659abb108a	3cf3069d5574ae9ad1385068364f1b0a13e9bf51ef3dfe8e280dae67a8058cd8	v1	Backend Engineer 15	backend engineer 15	\N	Fixture Co 15	fixture co 15	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:40.367358+00	2026-09-27 14:12:40.367358+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
2be0d9b6-4548-47c7-aceb-94d620276fb4	a581dbbe2cf11b7c7c5f171d67631f09b71bd3aa9b910addc6160fbd18d71432	v1	Backend Engineer 1	backend engineer 1	\N	Fixture Co 1	fixture co 1	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:40.397452+00	2026-09-27 14:12:40.397452+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
250947ce-2088-40f9-b6c3-d0b862f77c4b	6bcfb3abdde34d7428895e6467b109ab15a0344a3c850fa9b3308c655a305787	v1	Backend Engineer 8	backend engineer 8	\N	Fixture Co 8	fixture co 8	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:40.426798+00	2026-09-27 14:12:40.426798+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
ff7083e5-4ce4-47a9-9860-f1f3f76196f8	41324d20f70a3846d3e2dbb4641df384e91fb2e82d86a17fd0b10fb7a0c69197	v1	Backend Engineer 10	backend engineer 10	\N	Fixture Co 10	fixture co 10	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:40.46066+00	2026-09-27 14:12:40.46066+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
b06fb893-8eab-43aa-8a5c-75166ca22149	0d31233fbb7df6e7a1c07f33b20f733ddd913ccbadd353c8993914200a575a34	v1	Backend Engineer 7	backend engineer 7	\N	Fixture Co 7	fixture co 7	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:40.489952+00	2026-09-27 14:12:40.489952+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
9cde205b-712f-4f03-800f-c6445ad0a6eb	7e1a8adb4bdd521b33a6246d14b4600edc8eefe8bb50630502c7c2c9db9e7ffc	v1	Backend Engineer 5	backend engineer 5	\N	Fixture Co 5	fixture co 5	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:40.517839+00	2026-09-27 14:12:40.517839+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
5bb0d07c-99fa-447a-a6db-7ef00385ef86	9d58dd3ac953b7c8d0fff850151b2346c8a71ba2b1460068d544d46e9a299d3b	v1	Backend Engineer 6	backend engineer 6	\N	Fixture Co 6	fixture co 6	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:40.545721+00	2026-09-27 14:12:40.545721+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
e10b2104-35b5-41cf-a57d-50a454944ca4	c6435cae8b77841a1c1833e0388b2eadceb2a7fe9c6d307bc305270192aa4879	v1	Backend Engineer 16	backend engineer 16	\N	Fixture Co 16	fixture co 16	\N	\N	UNKNOWN	UNKNOWN	UNKNOWN	\N	DISCOVERED	\N	\N	2026-09-27 14:12:40.573753+00	2026-09-27 14:12:40.573753+00	1	\N	SOFTWARE_ENGINEERING	{"rule": "title", "term": "backend engineer", "origin": "title"}	role-family-v1	\N	\N	\N
\.


--
-- Data for Name: opportunity_compensation; Type: TABLE DATA; Schema: opportunities; Owner: -
--

COPY opportunities.opportunity_compensation (id, opportunity_id, amount_min, amount_max, currency, period, gross_net, evidence_text, evidence_source, normalizer_version, source_occurrence_id, raw_item_id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: opportunity_embedding; Type: TABLE DATA; Schema: opportunities; Owner: -
--

COPY opportunities.opportunity_embedding (opportunity_id, content_version, model, text_version, text_hash, dimensions, created_at, updated_at, embedding) FROM stdin;
\.


--
-- Data for Name: opportunity_embedding_failure; Type: TABLE DATA; Schema: opportunities; Owner: -
--

COPY opportunities.opportunity_embedding_failure (opportunity_id, content_version, model, text_version, failure_code, detail, attempts, first_failed_at, last_attempt_at) FROM stdin;
\.


--
-- Data for Name: opportunity_skill; Type: TABLE DATA; Schema: opportunities; Owner: -
--

COPY opportunities.opportunity_skill (id, opportunity_id, canonical_name, display_name, requirement, evidence, taxonomy_version, normalizer_version, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: relevance_mark; Type: TABLE DATA; Schema: opportunities; Owner: -
--

COPY opportunities.relevance_mark (id, opportunity_id, relevant, reason, note, profile_version_id, marked_at) FROM stdin;
\.


--
-- Data for Name: source_occurrence; Type: TABLE DATA; Schema: opportunities; Owner: -
--

COPY opportunities.source_occurrence (id, opportunity_id, raw_item_id, source_definition_id, external_id, source_url, normalized_source_url, first_seen_at, last_seen_at, source_published_at, source_updated_at, last_seen_run_id) FROM stdin;
a989ca0e-62f1-47c6-9c94-69d5f9719cd6	bee90be5-75fe-427d-8d6d-e8e6e47a327c	005a6afe-f63e-4bb8-be0b-5fd2724742ec	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:5849c08da41a8433844df1d59e04533df57d9b95f94c0b59c8ba1c79aea50b83	https://example.com/jobs/fixture-18	https://example.com/jobs/fixture-18	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
b560e4d3-1185-4768-9d17-9a4039d3d521	19f8b07d-e01e-4034-bee9-a3b50cdfbca9	19a81372-2092-4385-9b5f-0388cee53e81	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:71209897cdea7a33d788be4131e04e526a866735ff44958dbcf3d297ddbe6800	https://example.com/jobs/fixture-3	https://example.com/jobs/fixture-3	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
240b3b3f-7402-4b22-b1e1-afeb9e64334d	90899efb-4717-4405-b1fd-56715206c652	1c07155c-5c37-44d7-83ff-a4ea4ff9cb48	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:5c6a0436a40fa7213c38747aa775bc5fa731a3d70b4575489fa70ccad0776bbf	https://example.com/jobs/fixture-20	https://example.com/jobs/fixture-20	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
d7facc58-1d17-48ee-b64c-8092758f44d6	ce6090b9-0047-4163-bda3-e30c584ca2a6	310610b2-1e99-4e78-bedd-d364383c35f2	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:42b3a95cc10610805faceb52dc5e5776b0cf26c1b2692568c01768a9d814c06b	https://example.com/jobs/fixture-14	https://example.com/jobs/fixture-14	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
5c3dedc5-6e21-493c-b950-25919f90c7f8	8be53612-77cc-4a96-b3c1-3c281a5f5e1b	388fd30a-292b-4128-88f4-c7d808828dfa	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:030a31257f065474abe57b1fba4b67152dc586f8cf51c1c6a1e9f54c014eda23	https://example.com/jobs/fixture-2	https://example.com/jobs/fixture-2	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
28331fdb-0550-4fb1-96e3-14d08cb35f8c	3f2a8e86-3098-4a3d-9d57-b8d9bfcb7bc1	49b4b3a7-be04-4077-8a3a-634ce5b9cd02	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:b12129a4d89404aa0d6183fe41911719e491ad477651ab33c1ef676673472f78	https://example.com/jobs/fixture-19	https://example.com/jobs/fixture-19	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
a97d3b54-6fd8-47fc-9892-68902ee96364	153df84e-624a-4856-83aa-0004a6ebfd6d	4d7cfa7b-2c02-442b-8339-9361412c006e	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:05c3586acd0d9d08fd5d1e0b1ef57b2efde38c9a777c94ceaa446e8775f99269	https://example.com/jobs/fixture-9	https://example.com/jobs/fixture-9	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
77e3279f-3d01-49b9-925e-15a3367a9036	9dda9b23-9578-475e-9acc-e1df926d3b43	818b70a4-9057-4d51-b19c-832c8c2bf892	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:a0b605271e219aa0ef4e53e0870a15d88a70cfb5e06b7b9a2189c531d6da22f7	https://example.com/jobs/fixture-12	https://example.com/jobs/fixture-12	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
cdf5a757-60e7-47c8-825a-e90af5d6d01f	ce3258fe-4210-4da6-9125-e7220435fed0	9a2bb19b-7935-4087-84bb-1af773401c4f	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:b786102d1858ff6ca43c3f0b695e2da49291adeda5f6745d8c7f684a11be27e9	https://example.com/jobs/fixture-13	https://example.com/jobs/fixture-13	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
d98eb29a-3e9f-4458-832b-41700b01f2e6	b14215c9-2d59-4a44-b1a9-34bfb26f2381	ae475ec9-60db-4ba8-a5f5-3ce782d31ba8	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:06401d67faeeb840296203b157354ca312d8062a5d2badf760aa0f3e238761d0	https://example.com/jobs/fixture-4	https://example.com/jobs/fixture-4	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
db04a940-df97-46f4-b27c-1dda956b13f2	70cd12cc-58ca-41b0-9e2b-e0854711afae	b092dfbc-4e40-4399-9f75-c577d698e8b4	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:d0bd0e5b4c32b809ec9289322a16c1667bd405385f0ac8102b9b6af6004acefb	https://example.com/jobs/fixture-11	https://example.com/jobs/fixture-11	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
9d89cb60-495a-4dd2-a24c-846c70e27af6	3c4f5629-114a-41b5-b8f4-40615d03dc63	bc90a2a2-91db-4e49-97ab-bf19066397a2	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:be625f5041c178b85e75a0916ab71a7dd13e20ae583cfb52bf6f766bd0172da9	https://example.com/jobs/fixture-17	https://example.com/jobs/fixture-17	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
7fd616a1-9b53-4c9b-b5b3-b02e5fec247f	08224078-8512-4a17-9cbe-02659abb108a	c6e2a518-f82e-4a0e-9f10-c9fd035795eb	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:3e31cdb1e9b7fb0a0ef2396e57301faafc3de74b5c9426d7402709a5a09cfb0f	https://example.com/jobs/fixture-15	https://example.com/jobs/fixture-15	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
472373f5-b490-4d54-9c8d-a6233a290cd3	2be0d9b6-4548-47c7-aceb-94d620276fb4	ca12553c-e8ba-4220-ab51-39fd091bdc0d	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:660070ed895ce85432bd51a75bad92b7bbe866b68de5d28aebe2dc146681e269	https://example.com/jobs/fixture-1	https://example.com/jobs/fixture-1	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
b0bddb69-7203-4475-958b-acffa10e0099	250947ce-2088-40f9-b6c3-d0b862f77c4b	dfad672c-01cf-49bd-91a7-7c39211e0dfb	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:b2224cdc97235adf062a0b3a4d97df162c5a32746cfb00e480d477cda326b0a0	https://example.com/jobs/fixture-8	https://example.com/jobs/fixture-8	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
7a1b5117-ed45-4a68-b37e-b99a65d37b77	ff7083e5-4ce4-47a9-9860-f1f3f76196f8	e169598b-42d5-4267-97fb-ea83d2f49ac8	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:7daa647023aaf2b6c18f60120f2a37177b3aab59e02f82e2a4a350d2f9f47db1	https://example.com/jobs/fixture-10	https://example.com/jobs/fixture-10	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
7d6bf222-e712-4870-a9d4-9b1ef2894169	b06fb893-8eab-43aa-8a5c-75166ca22149	e967f036-6280-4f34-b6ff-7befdfc8d318	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:20181322df4dea864afcd94a9f80e04c7374b1a60a6a81fb4f4dcdb753fb9bfd	https://example.com/jobs/fixture-7	https://example.com/jobs/fixture-7	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
d843975e-4a0f-43f8-bab2-4aa016309227	9cde205b-712f-4f03-800f-c6445ad0a6eb	f129b7e1-36bc-425a-b971-01ade87c32fd	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:0ac97018a871e19176b044e5b34b1720192de0dfc3efd9badb0bb97faca8fa44	https://example.com/jobs/fixture-5	https://example.com/jobs/fixture-5	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
b9e9e2a7-d1fa-4387-8c51-bb2a406a0128	5bb0d07c-99fa-447a-a6db-7ef00385ef86	f33ac04f-b48f-4216-bbd6-5f9bcf539907	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:63bbebc4e764b6b4d53f9e0a86db183a89f4bb9df34fb9d3da6a48dea0ada4e9	https://example.com/jobs/fixture-6	https://example.com/jobs/fixture-6	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
cdf79f4b-c37b-4212-b200-dc11b08e7ac0	e10b2104-35b5-41cf-a57d-50a454944ca4	ff51a452-8ba7-434f-b9d6-f1f841726c80	70fc1c6e-df43-41fe-a141-71cc15469cbf	manual:fd796cb9a7332eec5ea0947c141f790468b38f4f39dbbd7591aed815bd4a6b74	https://example.com/jobs/fixture-16	https://example.com/jobs/fixture-16	2026-09-27 14:12:24.805155+00	2026-09-27 14:12:24.816713+00	\N	\N	e28ae9d8-50a0-4603-9c28-a0172362188c
\.


--
-- Data for Name: worker_job_state; Type: TABLE DATA; Schema: platform; Owner: -
--

COPY platform.worker_job_state (job_name, last_attempt_at, last_success_at, last_failure_at, last_duration_ms, next_run_at, last_correlation_id, last_error) FROM stdin;
\.


--
-- Data for Name: career_profile; Type: TABLE DATA; Schema: profile; Owner: -
--

COPY profile.career_profile (id, singleton_key, version, created_at) FROM stdin;
9ccb39af-9bc0-4884-9390-34f2d0ca1afb	t	1	2026-09-27 14:13:03.867857+00
\.


--
-- Data for Name: employment_preference; Type: TABLE DATA; Schema: profile; Owner: -
--

COPY profile.employment_preference (id, profile_version_id, work_modes, contracts, countries, timezone_start_hour, timezone_end_hour, compensation_min, compensation_max, compensation_currency, relocation_allowed, sponsorship_required, compensation_period, target_role_families) FROM stdin;
ffb4d7dc-c00f-4364-9dc0-556454ea63dc	ba87f661-4299-4fdd-bc69-12f182e3e2dc	{remote}	{clt}	{BR}	\N	\N	\N	\N	\N	f	f	\N	{}
\.


--
-- Data for Name: experience; Type: TABLE DATA; Schema: profile; Owner: -
--

COPY profile.experience (id, profile_version_id, company_name, title, started_on, ended_on, summary) FROM stdin;
\.


--
-- Data for Name: profile_skill; Type: TABLE DATA; Schema: profile; Owner: -
--

COPY profile.profile_skill (id, profile_version_id, skill_id, level, last_used_at, experience_months) FROM stdin;
76a29a6e-ffd2-407a-a4a4-4939cc7ae799	ba87f661-4299-4fdd-bc69-12f182e3e2dc	7595a840-bc38-4d87-aec7-3b8aae73a90d	\N	\N	\N
2c62f147-ede5-4335-bdf3-31af571e70a5	ba87f661-4299-4fdd-bc69-12f182e3e2dc	3e959bb4-f470-4d18-82d4-e6b14691a3f7	\N	\N	\N
\.


--
-- Data for Name: profile_version; Type: TABLE DATA; Schema: profile; Owner: -
--

COPY profile.profile_version (id, career_profile_id, number, status, created_at, published_at, activated_at) FROM stdin;
ba87f661-4299-4fdd-bc69-12f182e3e2dc	9ccb39af-9bc0-4884-9390-34f2d0ca1afb	1	ACTIVE	2026-09-27 14:13:03.867857+00	2026-09-27 14:13:03.893466+00	2026-09-27 14:13:03.89783+00
\.


--
-- Data for Name: project; Type: TABLE DATA; Schema: profile; Owner: -
--

COPY profile.project (id, profile_version_id, name, started_on, ended_on, description, url) FROM stdin;
\.


--
-- Data for Name: skill; Type: TABLE DATA; Schema: profile; Owner: -
--

COPY profile.skill (id, canonical_name, display_name, created_at) FROM stdin;
7595a840-bc38-4d87-aec7-3b8aae73a90d	python	Python	2026-09-27 14:13:03.867857+00
3e959bb4-f470-4d18-82d4-e6b14691a3f7	sql	SQL	2026-09-27 14:13:03.867857+00
\.


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.alembic_version (version_num) FROM stdin;
20260925_0029
\.


--
-- Name: payload_retention_event payload_retention_event_pkey; Type: CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.payload_retention_event
    ADD CONSTRAINT payload_retention_event_pkey PRIMARY KEY (id);


--
-- Name: raw_item_payload raw_item_payload_pkey; Type: CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.raw_item_payload
    ADD CONSTRAINT raw_item_payload_pkey PRIMARY KEY (raw_item_id);


--
-- Name: raw_item raw_item_pkey; Type: CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.raw_item
    ADD CONSTRAINT raw_item_pkey PRIMARY KEY (id);


--
-- Name: source_alert_incident source_alert_incident_pkey; Type: CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.source_alert_incident
    ADD CONSTRAINT source_alert_incident_pkey PRIMARY KEY (id);


--
-- Name: source_checkpoint source_checkpoint_pkey; Type: CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.source_checkpoint
    ADD CONSTRAINT source_checkpoint_pkey PRIMARY KEY (source_definition_id);


--
-- Name: source_definition source_definition_pkey; Type: CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.source_definition
    ADD CONSTRAINT source_definition_pkey PRIMARY KEY (id);


--
-- Name: source_probe source_probe_pkey; Type: CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.source_probe
    ADD CONSTRAINT source_probe_pkey PRIMARY KEY (id);


--
-- Name: source_run source_run_pkey; Type: CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.source_run
    ADD CONSTRAINT source_run_pkey PRIMARY KEY (id);


--
-- Name: payload_retention_event uq_payload_retention_event_raw_item; Type: CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.payload_retention_event
    ADD CONSTRAINT uq_payload_retention_event_raw_item UNIQUE (raw_item_id);


--
-- Name: raw_item uq_raw_item_source_identity_hash; Type: CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.raw_item
    ADD CONSTRAINT uq_raw_item_source_identity_hash UNIQUE (source_definition_id, identity_key, payload_hash);


--
-- Name: source_definition uq_source_definition_type_name; Type: CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.source_definition
    ADD CONSTRAINT uq_source_definition_type_name UNIQUE (source_type, name);


--
-- Name: company_alias company_alias_pkey; Type: CONSTRAINT; Schema: company_radar; Owner: -
--

ALTER TABLE ONLY company_radar.company_alias
    ADD CONSTRAINT company_alias_pkey PRIMARY KEY (id);


--
-- Name: company_import_batch company_import_batch_pkey; Type: CONSTRAINT; Schema: company_radar; Owner: -
--

ALTER TABLE ONLY company_radar.company_import_batch
    ADD CONSTRAINT company_import_batch_pkey PRIMARY KEY (id);


--
-- Name: company_import_issue company_import_issue_pkey; Type: CONSTRAINT; Schema: company_radar; Owner: -
--

ALTER TABLE ONLY company_radar.company_import_issue
    ADD CONSTRAINT company_import_issue_pkey PRIMARY KEY (id);


--
-- Name: company company_pkey; Type: CONSTRAINT; Schema: company_radar; Owner: -
--

ALTER TABLE ONLY company_radar.company
    ADD CONSTRAINT company_pkey PRIMARY KEY (id);


--
-- Name: company_source company_source_pkey; Type: CONSTRAINT; Schema: company_radar; Owner: -
--

ALTER TABLE ONLY company_radar.company_source
    ADD CONSTRAINT company_source_pkey PRIMARY KEY (id);


--
-- Name: company_source_revision company_source_revision_pkey; Type: CONSTRAINT; Schema: company_radar; Owner: -
--

ALTER TABLE ONLY company_radar.company_source_revision
    ADD CONSTRAINT company_source_revision_pkey PRIMARY KEY (id);


--
-- Name: company_alias uq_company_alias_company_normalized; Type: CONSTRAINT; Schema: company_radar; Owner: -
--

ALTER TABLE ONLY company_radar.company_alias
    ADD CONSTRAINT uq_company_alias_company_normalized UNIQUE (company_id, normalized_alias);


--
-- Name: company uq_company_domain; Type: CONSTRAINT; Schema: company_radar; Owner: -
--

ALTER TABLE ONLY company_radar.company
    ADD CONSTRAINT uq_company_domain UNIQUE (domain);


--
-- Name: company_import_batch uq_company_import_batch_file_hash; Type: CONSTRAINT; Schema: company_radar; Owner: -
--

ALTER TABLE ONLY company_radar.company_import_batch
    ADD CONSTRAINT uq_company_import_batch_file_hash UNIQUE (file_hash);


--
-- Name: company uq_company_normalized_name; Type: CONSTRAINT; Schema: company_radar; Owner: -
--

ALTER TABLE ONLY company_radar.company
    ADD CONSTRAINT uq_company_normalized_name UNIQUE (normalized_name);


--
-- Name: company_source uq_company_source_company_type_endpoint; Type: CONSTRAINT; Schema: company_radar; Owner: -
--

ALTER TABLE ONLY company_radar.company_source
    ADD CONSTRAINT uq_company_source_company_type_endpoint UNIQUE (company_id, source_type, endpoint);


--
-- Name: company_source_revision uq_company_source_revision_source_version; Type: CONSTRAINT; Schema: company_radar; Owner: -
--

ALTER TABLE ONLY company_radar.company_source_revision
    ADD CONSTRAINT uq_company_source_revision_source_version UNIQUE (company_source_id, version);


--
-- Name: application_process application_process_pkey; Type: CONSTRAINT; Schema: crm; Owner: -
--

ALTER TABLE ONLY crm.application_process
    ADD CONSTRAINT application_process_pkey PRIMARY KEY (id);


--
-- Name: stage_history stage_history_pkey; Type: CONSTRAINT; Schema: crm; Owner: -
--

ALTER TABLE ONLY crm.stage_history
    ADD CONSTRAINT stage_history_pkey PRIMARY KEY (id);


--
-- Name: match_analysis_claim match_analysis_claim_pkey; Type: CONSTRAINT; Schema: matching; Owner: -
--

ALTER TABLE ONLY matching.match_analysis_claim
    ADD CONSTRAINT match_analysis_claim_pkey PRIMARY KEY (assessment_id);


--
-- Name: match_analysis match_analysis_pkey; Type: CONSTRAINT; Schema: matching; Owner: -
--

ALTER TABLE ONLY matching.match_analysis
    ADD CONSTRAINT match_analysis_pkey PRIMARY KEY (id);


--
-- Name: match_assessment match_assessment_pkey; Type: CONSTRAINT; Schema: matching; Owner: -
--

ALTER TABLE ONLY matching.match_assessment
    ADD CONSTRAINT match_assessment_pkey PRIMARY KEY (id);


--
-- Name: match_factor match_factor_pkey; Type: CONSTRAINT; Schema: matching; Owner: -
--

ALTER TABLE ONLY matching.match_factor
    ADD CONSTRAINT match_factor_pkey PRIMARY KEY (id);


--
-- Name: match_assessment uq_match_assessment_input_hash; Type: CONSTRAINT; Schema: matching; Owner: -
--

ALTER TABLE ONLY matching.match_assessment
    ADD CONSTRAINT uq_match_assessment_input_hash UNIQUE (input_hash);


--
-- Name: match_factor uq_match_factor_assessment_code; Type: CONSTRAINT; Schema: matching; Owner: -
--

ALTER TABLE ONLY matching.match_factor
    ADD CONSTRAINT uq_match_factor_assessment_code UNIQUE (assessment_id, factor_code);


--
-- Name: normalization_result normalization_result_pkey; Type: CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.normalization_result
    ADD CONSTRAINT normalization_result_pkey PRIMARY KEY (id);


--
-- Name: opportunity_compensation opportunity_compensation_pkey; Type: CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.opportunity_compensation
    ADD CONSTRAINT opportunity_compensation_pkey PRIMARY KEY (id);


--
-- Name: opportunity_embedding_failure opportunity_embedding_failure_pkey; Type: CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.opportunity_embedding_failure
    ADD CONSTRAINT opportunity_embedding_failure_pkey PRIMARY KEY (opportunity_id);


--
-- Name: opportunity_embedding opportunity_embedding_pkey; Type: CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.opportunity_embedding
    ADD CONSTRAINT opportunity_embedding_pkey PRIMARY KEY (opportunity_id);


--
-- Name: opportunity opportunity_pkey; Type: CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.opportunity
    ADD CONSTRAINT opportunity_pkey PRIMARY KEY (id);


--
-- Name: opportunity_skill opportunity_skill_pkey; Type: CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.opportunity_skill
    ADD CONSTRAINT opportunity_skill_pkey PRIMARY KEY (id);


--
-- Name: relevance_mark relevance_mark_pkey; Type: CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.relevance_mark
    ADD CONSTRAINT relevance_mark_pkey PRIMARY KEY (id);


--
-- Name: source_occurrence source_occurrence_pkey; Type: CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.source_occurrence
    ADD CONSTRAINT source_occurrence_pkey PRIMARY KEY (id);


--
-- Name: normalization_result uq_normalization_result_raw_version; Type: CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.normalization_result
    ADD CONSTRAINT uq_normalization_result_raw_version UNIQUE (raw_item_id, normalizer_version);


--
-- Name: opportunity_compensation uq_opportunity_compensation_source_occurrence; Type: CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.opportunity_compensation
    ADD CONSTRAINT uq_opportunity_compensation_source_occurrence UNIQUE (source_occurrence_id);


--
-- Name: opportunity uq_opportunity_fingerprint_version_value; Type: CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.opportunity
    ADD CONSTRAINT uq_opportunity_fingerprint_version_value UNIQUE (fingerprint_version, fingerprint);


--
-- Name: opportunity_skill uq_opportunity_skill_opportunity_name_taxonomy; Type: CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.opportunity_skill
    ADD CONSTRAINT uq_opportunity_skill_opportunity_name_taxonomy UNIQUE (opportunity_id, canonical_name, taxonomy_version);


--
-- Name: source_occurrence uq_source_occurrence_raw_item; Type: CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.source_occurrence
    ADD CONSTRAINT uq_source_occurrence_raw_item UNIQUE (raw_item_id);


--
-- Name: worker_job_state worker_job_state_pkey; Type: CONSTRAINT; Schema: platform; Owner: -
--

ALTER TABLE ONLY platform.worker_job_state
    ADD CONSTRAINT worker_job_state_pkey PRIMARY KEY (job_name);


--
-- Name: career_profile career_profile_pkey; Type: CONSTRAINT; Schema: profile; Owner: -
--

ALTER TABLE ONLY profile.career_profile
    ADD CONSTRAINT career_profile_pkey PRIMARY KEY (id);


--
-- Name: employment_preference employment_preference_pkey; Type: CONSTRAINT; Schema: profile; Owner: -
--

ALTER TABLE ONLY profile.employment_preference
    ADD CONSTRAINT employment_preference_pkey PRIMARY KEY (id);


--
-- Name: experience experience_pkey; Type: CONSTRAINT; Schema: profile; Owner: -
--

ALTER TABLE ONLY profile.experience
    ADD CONSTRAINT experience_pkey PRIMARY KEY (id);


--
-- Name: profile_skill profile_skill_pkey; Type: CONSTRAINT; Schema: profile; Owner: -
--

ALTER TABLE ONLY profile.profile_skill
    ADD CONSTRAINT profile_skill_pkey PRIMARY KEY (id);


--
-- Name: profile_version profile_version_pkey; Type: CONSTRAINT; Schema: profile; Owner: -
--

ALTER TABLE ONLY profile.profile_version
    ADD CONSTRAINT profile_version_pkey PRIMARY KEY (id);


--
-- Name: project project_pkey; Type: CONSTRAINT; Schema: profile; Owner: -
--

ALTER TABLE ONLY profile.project
    ADD CONSTRAINT project_pkey PRIMARY KEY (id);


--
-- Name: skill skill_pkey; Type: CONSTRAINT; Schema: profile; Owner: -
--

ALTER TABLE ONLY profile.skill
    ADD CONSTRAINT skill_pkey PRIMARY KEY (id);


--
-- Name: career_profile uq_career_profile_singleton_key; Type: CONSTRAINT; Schema: profile; Owner: -
--

ALTER TABLE ONLY profile.career_profile
    ADD CONSTRAINT uq_career_profile_singleton_key UNIQUE (singleton_key);


--
-- Name: employment_preference uq_preference_profile_version; Type: CONSTRAINT; Schema: profile; Owner: -
--

ALTER TABLE ONLY profile.employment_preference
    ADD CONSTRAINT uq_preference_profile_version UNIQUE (profile_version_id);


--
-- Name: profile_skill uq_profile_skill_version_skill; Type: CONSTRAINT; Schema: profile; Owner: -
--

ALTER TABLE ONLY profile.profile_skill
    ADD CONSTRAINT uq_profile_skill_version_skill UNIQUE (profile_version_id, skill_id);


--
-- Name: profile_version uq_profile_version_number; Type: CONSTRAINT; Schema: profile; Owner: -
--

ALTER TABLE ONLY profile.profile_version
    ADD CONSTRAINT uq_profile_version_number UNIQUE (career_profile_id, number);


--
-- Name: skill uq_skill_canonical_name; Type: CONSTRAINT; Schema: profile; Owner: -
--

ALTER TABLE ONLY profile.skill
    ADD CONSTRAINT uq_skill_canonical_name UNIQUE (canonical_name);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: ix_payload_retention_event_expired_at; Type: INDEX; Schema: acquisition; Owner: -
--

CREATE INDEX ix_payload_retention_event_expired_at ON acquisition.payload_retention_event USING btree (expired_at);


--
-- Name: ix_raw_item_source_run; Type: INDEX; Schema: acquisition; Owner: -
--

CREATE INDEX ix_raw_item_source_run ON acquisition.raw_item USING btree (source_run_id);


--
-- Name: ix_source_alert_incident_source_opened; Type: INDEX; Schema: acquisition; Owner: -
--

CREATE INDEX ix_source_alert_incident_source_opened ON acquisition.source_alert_incident USING btree (source_definition_id, opened_at);


--
-- Name: ix_source_definition_company_source; Type: INDEX; Schema: acquisition; Owner: -
--

CREATE INDEX ix_source_definition_company_source ON acquisition.source_definition USING btree (company_source_id);


--
-- Name: ix_source_probe_source_started; Type: INDEX; Schema: acquisition; Owner: -
--

CREATE INDEX ix_source_probe_source_started ON acquisition.source_probe USING btree (source_definition_id, started_at);


--
-- Name: ix_source_run_source_started; Type: INDEX; Schema: acquisition; Owner: -
--

CREATE INDEX ix_source_run_source_started ON acquisition.source_run USING btree (source_definition_id, started_at);


--
-- Name: uq_source_alert_incident_open; Type: INDEX; Schema: acquisition; Owner: -
--

CREATE UNIQUE INDEX uq_source_alert_incident_open ON acquisition.source_alert_incident USING btree (source_definition_id) WHERE (recovered_at IS NULL);


--
-- Name: uq_source_run_active; Type: INDEX; Schema: acquisition; Owner: -
--

CREATE UNIQUE INDEX uq_source_run_active ON acquisition.source_run USING btree (source_definition_id) WHERE ((status)::text = ANY ((ARRAY['PENDING'::character varying, 'RUNNING'::character varying])::text[]));


--
-- Name: ix_company_alias_normalized_alias; Type: INDEX; Schema: company_radar; Owner: -
--

CREATE INDEX ix_company_alias_normalized_alias ON company_radar.company_alias USING btree (normalized_alias);


--
-- Name: ix_company_normalized_name; Type: INDEX; Schema: company_radar; Owner: -
--

CREATE INDEX ix_company_normalized_name ON company_radar.company USING btree (normalized_name);


--
-- Name: ix_application_next_action_at; Type: INDEX; Schema: crm; Owner: -
--

CREATE INDEX ix_application_next_action_at ON crm.application_process USING btree (next_action_at);


--
-- Name: ix_application_stage_updated; Type: INDEX; Schema: crm; Owner: -
--

CREATE INDEX ix_application_stage_updated ON crm.application_process USING btree (current_stage, updated_at);


--
-- Name: ix_stage_history_application; Type: INDEX; Schema: crm; Owner: -
--

CREATE INDEX ix_stage_history_application ON crm.stage_history USING btree (application_id, occurred_at);


--
-- Name: uq_application_active; Type: INDEX; Schema: crm; Owner: -
--

CREATE UNIQUE INDEX uq_application_active ON crm.application_process USING btree (opportunity_id, profile_version_id) WHERE ((status)::text = 'ACTIVE'::text);


--
-- Name: ix_match_analysis_assessment_analyzed; Type: INDEX; Schema: matching; Owner: -
--

CREATE INDEX ix_match_analysis_assessment_analyzed ON matching.match_analysis USING btree (assessment_id, analyzed_at);


--
-- Name: ix_match_analysis_cache_key; Type: INDEX; Schema: matching; Owner: -
--

CREATE INDEX ix_match_analysis_cache_key ON matching.match_analysis USING btree (cache_key);


--
-- Name: ix_match_analysis_claim_expires_at; Type: INDEX; Schema: matching; Owner: -
--

CREATE INDEX ix_match_analysis_claim_expires_at ON matching.match_analysis_claim USING btree (expires_at);


--
-- Name: ix_match_analysis_key_version; Type: INDEX; Schema: matching; Owner: -
--

CREATE INDEX ix_match_analysis_key_version ON matching.match_analysis USING btree (cache_key, key_version);


--
-- Name: ix_match_assessment_opportunity_profile_created; Type: INDEX; Schema: matching; Owner: -
--

CREATE INDEX ix_match_assessment_opportunity_profile_created ON matching.match_assessment USING btree (opportunity_id, profile_version_id, created_at);


--
-- Name: ix_match_factor_assessment; Type: INDEX; Schema: matching; Owner: -
--

CREATE INDEX ix_match_factor_assessment ON matching.match_factor USING btree (assessment_id);


--
-- Name: ix_opportunity_allowed_countries; Type: INDEX; Schema: opportunities; Owner: -
--

CREATE INDEX ix_opportunity_allowed_countries ON opportunities.opportunity USING gin (allowed_countries);


--
-- Name: ix_opportunity_company_status; Type: INDEX; Schema: opportunities; Owner: -
--

CREATE INDEX ix_opportunity_company_status ON opportunities.opportunity USING btree (canonical_company_id, lifecycle_status);


--
-- Name: ix_opportunity_compensation_currency_period; Type: INDEX; Schema: opportunities; Owner: -
--

CREATE INDEX ix_opportunity_compensation_currency_period ON opportunities.opportunity_compensation USING btree (currency, period);


--
-- Name: ix_opportunity_embedding_hnsw; Type: INDEX; Schema: opportunities; Owner: -
--

CREATE INDEX ix_opportunity_embedding_hnsw ON opportunities.opportunity_embedding USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: ix_opportunity_published; Type: INDEX; Schema: opportunities; Owner: -
--

CREATE INDEX ix_opportunity_published ON opportunities.opportunity USING btree (published_at);


--
-- Name: ix_opportunity_role_family; Type: INDEX; Schema: opportunities; Owner: -
--

CREATE INDEX ix_opportunity_role_family ON opportunities.opportunity USING btree (role_family);


--
-- Name: ix_opportunity_search_document; Type: INDEX; Schema: opportunities; Owner: -
--

CREATE INDEX ix_opportunity_search_document ON opportunities.opportunity USING gin (search_document);


--
-- Name: ix_opportunity_skill_requirement; Type: INDEX; Schema: opportunities; Owner: -
--

CREATE INDEX ix_opportunity_skill_requirement ON opportunities.opportunity_skill USING btree (requirement);


--
-- Name: ix_relevance_mark_opportunity_marked_at; Type: INDEX; Schema: opportunities; Owner: -
--

CREATE INDEX ix_relevance_mark_opportunity_marked_at ON opportunities.relevance_mark USING btree (opportunity_id, marked_at);


--
-- Name: ix_source_occurrence_normalized_url; Type: INDEX; Schema: opportunities; Owner: -
--

CREATE INDEX ix_source_occurrence_normalized_url ON opportunities.source_occurrence USING btree (normalized_source_url);


--
-- Name: ix_source_occurrence_source_url; Type: INDEX; Schema: opportunities; Owner: -
--

CREATE INDEX ix_source_occurrence_source_url ON opportunities.source_occurrence USING btree (source_url);


--
-- Name: uq_source_occurrence_source_external; Type: INDEX; Schema: opportunities; Owner: -
--

CREATE UNIQUE INDEX uq_source_occurrence_source_external ON opportunities.source_occurrence USING btree (source_definition_id, external_id) WHERE (external_id IS NOT NULL);


--
-- Name: uq_source_occurrence_source_url_fallback; Type: INDEX; Schema: opportunities; Owner: -
--

CREATE UNIQUE INDEX uq_source_occurrence_source_url_fallback ON opportunities.source_occurrence USING btree (source_definition_id, normalized_source_url) WHERE ((external_id IS NULL) AND (normalized_source_url IS NOT NULL));


--
-- Name: uq_profile_version_active; Type: INDEX; Schema: profile; Owner: -
--

CREATE UNIQUE INDEX uq_profile_version_active ON profile.profile_version USING btree (career_profile_id) WHERE ((status)::text = 'ACTIVE'::text);


--
-- Name: stage_history trg_stage_history_immutable; Type: TRIGGER; Schema: crm; Owner: -
--

CREATE TRIGGER trg_stage_history_immutable BEFORE UPDATE ON crm.stage_history FOR EACH ROW EXECUTE FUNCTION crm.prevent_stage_history_mutation();


--
-- Name: match_analysis trg_match_analysis_immutable; Type: TRIGGER; Schema: matching; Owner: -
--

CREATE TRIGGER trg_match_analysis_immutable BEFORE UPDATE ON matching.match_analysis FOR EACH ROW EXECUTE FUNCTION matching.prevent_match_analysis_mutation();


--
-- Name: match_assessment trg_match_assessment_immutable; Type: TRIGGER; Schema: matching; Owner: -
--

CREATE TRIGGER trg_match_assessment_immutable BEFORE DELETE OR UPDATE ON matching.match_assessment FOR EACH ROW EXECUTE FUNCTION matching.prevent_match_assessment_mutation();


--
-- Name: match_factor trg_match_factor_immutable; Type: TRIGGER; Schema: matching; Owner: -
--

CREATE TRIGGER trg_match_factor_immutable BEFORE DELETE OR UPDATE ON matching.match_factor FOR EACH ROW EXECUTE FUNCTION matching.prevent_match_factor_mutation();


--
-- Name: payload_retention_event payload_retention_event_raw_item_id_fkey; Type: FK CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.payload_retention_event
    ADD CONSTRAINT payload_retention_event_raw_item_id_fkey FOREIGN KEY (raw_item_id) REFERENCES acquisition.raw_item(id) ON DELETE CASCADE;


--
-- Name: payload_retention_event payload_retention_event_source_definition_id_fkey; Type: FK CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.payload_retention_event
    ADD CONSTRAINT payload_retention_event_source_definition_id_fkey FOREIGN KEY (source_definition_id) REFERENCES acquisition.source_definition(id) ON DELETE CASCADE;


--
-- Name: raw_item_payload raw_item_payload_raw_item_id_fkey; Type: FK CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.raw_item_payload
    ADD CONSTRAINT raw_item_payload_raw_item_id_fkey FOREIGN KEY (raw_item_id) REFERENCES acquisition.raw_item(id) ON DELETE CASCADE;


--
-- Name: raw_item raw_item_source_definition_id_fkey; Type: FK CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.raw_item
    ADD CONSTRAINT raw_item_source_definition_id_fkey FOREIGN KEY (source_definition_id) REFERENCES acquisition.source_definition(id) ON DELETE RESTRICT;


--
-- Name: raw_item raw_item_source_run_id_fkey; Type: FK CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.raw_item
    ADD CONSTRAINT raw_item_source_run_id_fkey FOREIGN KEY (source_run_id) REFERENCES acquisition.source_run(id) ON DELETE RESTRICT;


--
-- Name: source_alert_incident source_alert_incident_opened_by_run_id_fkey; Type: FK CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.source_alert_incident
    ADD CONSTRAINT source_alert_incident_opened_by_run_id_fkey FOREIGN KEY (opened_by_run_id) REFERENCES acquisition.source_run(id) ON DELETE SET NULL;


--
-- Name: source_alert_incident source_alert_incident_recovered_by_run_id_fkey; Type: FK CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.source_alert_incident
    ADD CONSTRAINT source_alert_incident_recovered_by_run_id_fkey FOREIGN KEY (recovered_by_run_id) REFERENCES acquisition.source_run(id) ON DELETE SET NULL;


--
-- Name: source_alert_incident source_alert_incident_source_definition_id_fkey; Type: FK CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.source_alert_incident
    ADD CONSTRAINT source_alert_incident_source_definition_id_fkey FOREIGN KEY (source_definition_id) REFERENCES acquisition.source_definition(id) ON DELETE CASCADE;


--
-- Name: source_checkpoint source_checkpoint_promoted_by_run_id_fkey; Type: FK CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.source_checkpoint
    ADD CONSTRAINT source_checkpoint_promoted_by_run_id_fkey FOREIGN KEY (promoted_by_run_id) REFERENCES acquisition.source_run(id) ON DELETE RESTRICT;


--
-- Name: source_checkpoint source_checkpoint_source_definition_id_fkey; Type: FK CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.source_checkpoint
    ADD CONSTRAINT source_checkpoint_source_definition_id_fkey FOREIGN KEY (source_definition_id) REFERENCES acquisition.source_definition(id) ON DELETE CASCADE;


--
-- Name: source_definition source_definition_company_source_id_fkey; Type: FK CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.source_definition
    ADD CONSTRAINT source_definition_company_source_id_fkey FOREIGN KEY (company_source_id) REFERENCES company_radar.company_source(id) ON DELETE SET NULL;


--
-- Name: source_probe source_probe_source_definition_id_fkey; Type: FK CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.source_probe
    ADD CONSTRAINT source_probe_source_definition_id_fkey FOREIGN KEY (source_definition_id) REFERENCES acquisition.source_definition(id) ON DELETE CASCADE;


--
-- Name: source_run source_run_source_definition_id_fkey; Type: FK CONSTRAINT; Schema: acquisition; Owner: -
--

ALTER TABLE ONLY acquisition.source_run
    ADD CONSTRAINT source_run_source_definition_id_fkey FOREIGN KEY (source_definition_id) REFERENCES acquisition.source_definition(id) ON DELETE RESTRICT;


--
-- Name: company_alias company_alias_company_id_fkey; Type: FK CONSTRAINT; Schema: company_radar; Owner: -
--

ALTER TABLE ONLY company_radar.company_alias
    ADD CONSTRAINT company_alias_company_id_fkey FOREIGN KEY (company_id) REFERENCES company_radar.company(id) ON DELETE CASCADE;


--
-- Name: company_import_issue company_import_issue_batch_id_fkey; Type: FK CONSTRAINT; Schema: company_radar; Owner: -
--

ALTER TABLE ONLY company_radar.company_import_issue
    ADD CONSTRAINT company_import_issue_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES company_radar.company_import_batch(id) ON DELETE CASCADE;


--
-- Name: company_source company_source_company_id_fkey; Type: FK CONSTRAINT; Schema: company_radar; Owner: -
--

ALTER TABLE ONLY company_radar.company_source
    ADD CONSTRAINT company_source_company_id_fkey FOREIGN KEY (company_id) REFERENCES company_radar.company(id) ON DELETE CASCADE;


--
-- Name: company_source_revision company_source_revision_company_source_id_fkey; Type: FK CONSTRAINT; Schema: company_radar; Owner: -
--

ALTER TABLE ONLY company_radar.company_source_revision
    ADD CONSTRAINT company_source_revision_company_source_id_fkey FOREIGN KEY (company_source_id) REFERENCES company_radar.company_source(id) ON DELETE CASCADE;


--
-- Name: application_process application_process_opportunity_id_fkey; Type: FK CONSTRAINT; Schema: crm; Owner: -
--

ALTER TABLE ONLY crm.application_process
    ADD CONSTRAINT application_process_opportunity_id_fkey FOREIGN KEY (opportunity_id) REFERENCES opportunities.opportunity(id) ON DELETE RESTRICT;


--
-- Name: application_process application_process_profile_version_id_fkey; Type: FK CONSTRAINT; Schema: crm; Owner: -
--

ALTER TABLE ONLY crm.application_process
    ADD CONSTRAINT application_process_profile_version_id_fkey FOREIGN KEY (profile_version_id) REFERENCES profile.profile_version(id) ON DELETE RESTRICT;


--
-- Name: stage_history stage_history_application_id_fkey; Type: FK CONSTRAINT; Schema: crm; Owner: -
--

ALTER TABLE ONLY crm.stage_history
    ADD CONSTRAINT stage_history_application_id_fkey FOREIGN KEY (application_id) REFERENCES crm.application_process(id) ON DELETE CASCADE;


--
-- Name: match_analysis match_analysis_assessment_id_fkey; Type: FK CONSTRAINT; Schema: matching; Owner: -
--

ALTER TABLE ONLY matching.match_analysis
    ADD CONSTRAINT match_analysis_assessment_id_fkey FOREIGN KEY (assessment_id) REFERENCES matching.match_assessment(id) ON DELETE CASCADE;


--
-- Name: match_analysis_claim match_analysis_claim_assessment_id_fkey; Type: FK CONSTRAINT; Schema: matching; Owner: -
--

ALTER TABLE ONLY matching.match_analysis_claim
    ADD CONSTRAINT match_analysis_claim_assessment_id_fkey FOREIGN KEY (assessment_id) REFERENCES matching.match_assessment(id) ON DELETE CASCADE;


--
-- Name: match_assessment match_assessment_opportunity_id_fkey; Type: FK CONSTRAINT; Schema: matching; Owner: -
--

ALTER TABLE ONLY matching.match_assessment
    ADD CONSTRAINT match_assessment_opportunity_id_fkey FOREIGN KEY (opportunity_id) REFERENCES opportunities.opportunity(id) ON DELETE RESTRICT;


--
-- Name: match_assessment match_assessment_profile_version_id_fkey; Type: FK CONSTRAINT; Schema: matching; Owner: -
--

ALTER TABLE ONLY matching.match_assessment
    ADD CONSTRAINT match_assessment_profile_version_id_fkey FOREIGN KEY (profile_version_id) REFERENCES profile.profile_version(id) ON DELETE RESTRICT;


--
-- Name: match_factor match_factor_assessment_id_fkey; Type: FK CONSTRAINT; Schema: matching; Owner: -
--

ALTER TABLE ONLY matching.match_factor
    ADD CONSTRAINT match_factor_assessment_id_fkey FOREIGN KEY (assessment_id) REFERENCES matching.match_assessment(id) ON DELETE CASCADE;


--
-- Name: source_occurrence fk_source_occurrence_last_seen_run; Type: FK CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.source_occurrence
    ADD CONSTRAINT fk_source_occurrence_last_seen_run FOREIGN KEY (last_seen_run_id) REFERENCES acquisition.source_run(id) ON DELETE SET NULL;


--
-- Name: normalization_result normalization_result_opportunity_id_fkey; Type: FK CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.normalization_result
    ADD CONSTRAINT normalization_result_opportunity_id_fkey FOREIGN KEY (opportunity_id) REFERENCES opportunities.opportunity(id) ON DELETE CASCADE;


--
-- Name: normalization_result normalization_result_raw_item_id_fkey; Type: FK CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.normalization_result
    ADD CONSTRAINT normalization_result_raw_item_id_fkey FOREIGN KEY (raw_item_id) REFERENCES acquisition.raw_item(id) ON DELETE RESTRICT;


--
-- Name: normalization_result normalization_result_source_occurrence_id_fkey; Type: FK CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.normalization_result
    ADD CONSTRAINT normalization_result_source_occurrence_id_fkey FOREIGN KEY (source_occurrence_id) REFERENCES opportunities.source_occurrence(id) ON DELETE CASCADE;


--
-- Name: opportunity opportunity_canonical_company_id_fkey; Type: FK CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.opportunity
    ADD CONSTRAINT opportunity_canonical_company_id_fkey FOREIGN KEY (canonical_company_id) REFERENCES company_radar.company(id) ON DELETE SET NULL;


--
-- Name: opportunity_compensation opportunity_compensation_opportunity_id_fkey; Type: FK CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.opportunity_compensation
    ADD CONSTRAINT opportunity_compensation_opportunity_id_fkey FOREIGN KEY (opportunity_id) REFERENCES opportunities.opportunity(id) ON DELETE CASCADE;


--
-- Name: opportunity_compensation opportunity_compensation_raw_item_id_fkey; Type: FK CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.opportunity_compensation
    ADD CONSTRAINT opportunity_compensation_raw_item_id_fkey FOREIGN KEY (raw_item_id) REFERENCES acquisition.raw_item(id) ON DELETE RESTRICT;


--
-- Name: opportunity_compensation opportunity_compensation_source_occurrence_id_fkey; Type: FK CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.opportunity_compensation
    ADD CONSTRAINT opportunity_compensation_source_occurrence_id_fkey FOREIGN KEY (source_occurrence_id) REFERENCES opportunities.source_occurrence(id) ON DELETE CASCADE;


--
-- Name: opportunity_embedding_failure opportunity_embedding_failure_opportunity_id_fkey; Type: FK CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.opportunity_embedding_failure
    ADD CONSTRAINT opportunity_embedding_failure_opportunity_id_fkey FOREIGN KEY (opportunity_id) REFERENCES opportunities.opportunity(id) ON DELETE CASCADE;


--
-- Name: opportunity_embedding opportunity_embedding_opportunity_id_fkey; Type: FK CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.opportunity_embedding
    ADD CONSTRAINT opportunity_embedding_opportunity_id_fkey FOREIGN KEY (opportunity_id) REFERENCES opportunities.opportunity(id) ON DELETE CASCADE;


--
-- Name: opportunity_skill opportunity_skill_opportunity_id_fkey; Type: FK CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.opportunity_skill
    ADD CONSTRAINT opportunity_skill_opportunity_id_fkey FOREIGN KEY (opportunity_id) REFERENCES opportunities.opportunity(id) ON DELETE CASCADE;


--
-- Name: relevance_mark relevance_mark_opportunity_id_fkey; Type: FK CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.relevance_mark
    ADD CONSTRAINT relevance_mark_opportunity_id_fkey FOREIGN KEY (opportunity_id) REFERENCES opportunities.opportunity(id) ON DELETE CASCADE;


--
-- Name: relevance_mark relevance_mark_profile_version_id_fkey; Type: FK CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.relevance_mark
    ADD CONSTRAINT relevance_mark_profile_version_id_fkey FOREIGN KEY (profile_version_id) REFERENCES profile.profile_version(id) ON DELETE SET NULL;


--
-- Name: source_occurrence source_occurrence_opportunity_id_fkey; Type: FK CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.source_occurrence
    ADD CONSTRAINT source_occurrence_opportunity_id_fkey FOREIGN KEY (opportunity_id) REFERENCES opportunities.opportunity(id) ON DELETE CASCADE;


--
-- Name: source_occurrence source_occurrence_raw_item_id_fkey; Type: FK CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.source_occurrence
    ADD CONSTRAINT source_occurrence_raw_item_id_fkey FOREIGN KEY (raw_item_id) REFERENCES acquisition.raw_item(id) ON DELETE RESTRICT;


--
-- Name: source_occurrence source_occurrence_source_definition_id_fkey; Type: FK CONSTRAINT; Schema: opportunities; Owner: -
--

ALTER TABLE ONLY opportunities.source_occurrence
    ADD CONSTRAINT source_occurrence_source_definition_id_fkey FOREIGN KEY (source_definition_id) REFERENCES acquisition.source_definition(id) ON DELETE RESTRICT;


--
-- Name: employment_preference employment_preference_profile_version_id_fkey; Type: FK CONSTRAINT; Schema: profile; Owner: -
--

ALTER TABLE ONLY profile.employment_preference
    ADD CONSTRAINT employment_preference_profile_version_id_fkey FOREIGN KEY (profile_version_id) REFERENCES profile.profile_version(id) ON DELETE CASCADE;


--
-- Name: experience experience_profile_version_id_fkey; Type: FK CONSTRAINT; Schema: profile; Owner: -
--

ALTER TABLE ONLY profile.experience
    ADD CONSTRAINT experience_profile_version_id_fkey FOREIGN KEY (profile_version_id) REFERENCES profile.profile_version(id) ON DELETE CASCADE;


--
-- Name: profile_skill profile_skill_profile_version_id_fkey; Type: FK CONSTRAINT; Schema: profile; Owner: -
--

ALTER TABLE ONLY profile.profile_skill
    ADD CONSTRAINT profile_skill_profile_version_id_fkey FOREIGN KEY (profile_version_id) REFERENCES profile.profile_version(id) ON DELETE CASCADE;


--
-- Name: profile_skill profile_skill_skill_id_fkey; Type: FK CONSTRAINT; Schema: profile; Owner: -
--

ALTER TABLE ONLY profile.profile_skill
    ADD CONSTRAINT profile_skill_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES profile.skill(id);


--
-- Name: profile_version profile_version_career_profile_id_fkey; Type: FK CONSTRAINT; Schema: profile; Owner: -
--

ALTER TABLE ONLY profile.profile_version
    ADD CONSTRAINT profile_version_career_profile_id_fkey FOREIGN KEY (career_profile_id) REFERENCES profile.career_profile(id) ON DELETE CASCADE;


--
-- Name: project project_profile_version_id_fkey; Type: FK CONSTRAINT; Schema: profile; Owner: -
--

ALTER TABLE ONLY profile.project
    ADD CONSTRAINT project_profile_version_id_fkey FOREIGN KEY (profile_version_id) REFERENCES profile.profile_version(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

