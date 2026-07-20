--
-- PostgreSQL database dump
--

\restrict SgBgajTPDTcYYG3dTLcbqFbW7Si6aeGgJhh6TZzmbm7hLwPpiPnUjORDgbkufUi

-- Dumped from database version 18.0
-- Dumped by pg_dump version 18.0

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

ALTER TABLE IF EXISTS ONLY public.agv_map_roads DROP CONSTRAINT IF EXISTS agv_map_roads_map_id_fkey;
ALTER TABLE IF EXISTS ONLY public.agv_map_points DROP CONSTRAINT IF EXISTS agv_map_points_map_id_fkey;
ALTER TABLE IF EXISTS ONLY public.agv_map_codes DROP CONSTRAINT IF EXISTS agv_map_codes_map_id_fkey;
ALTER TABLE IF EXISTS ONLY public.agv_map_benziers DROP CONSTRAINT IF EXISTS agv_map_benziers_map_id_fkey;
DROP TRIGGER IF EXISTS trg_agv_devices_updated ON public.agv_devices;
DROP INDEX IF EXISTS public.idx_roads_map;
DROP INDEX IF EXISTS public.idx_points_map;
DROP INDEX IF EXISTS public.idx_map_points_team;
DROP INDEX IF EXISTS public.idx_int_logs_conn_time;
DROP INDEX IF EXISTS public.idx_codes_map;
DROP INDEX IF EXISTS public.idx_agv_devices_last_seen;
ALTER TABLE IF EXISTS ONLY public.agvs DROP CONSTRAINT IF EXISTS agvs_pkey;
ALTER TABLE IF EXISTS ONLY public.agvs DROP CONSTRAINT IF EXISTS agvs_agv_id_key;
ALTER TABLE IF EXISTS ONLY public.agv_workflow_templates DROP CONSTRAINT IF EXISTS agv_workflow_templates_template_id_key;
ALTER TABLE IF EXISTS ONLY public.agv_workflow_templates DROP CONSTRAINT IF EXISTS agv_workflow_templates_pkey;
ALTER TABLE IF EXISTS ONLY public.agv_tasks DROP CONSTRAINT IF EXISTS agv_tasks_task_id_key;
ALTER TABLE IF EXISTS ONLY public.agv_tasks DROP CONSTRAINT IF EXISTS agv_tasks_pkey;
ALTER TABLE IF EXISTS ONLY public.agv_task_executions DROP CONSTRAINT IF EXISTS agv_task_executions_pkey;
ALTER TABLE IF EXISTS ONLY public.agv_task_executions DROP CONSTRAINT IF EXISTS agv_task_executions_cmd_id_key;
ALTER TABLE IF EXISTS ONLY public.agv_schedules DROP CONSTRAINT IF EXISTS agv_schedules_pkey;
ALTER TABLE IF EXISTS ONLY public.agv_maps DROP CONSTRAINT IF EXISTS agv_maps_pkey;
ALTER TABLE IF EXISTS ONLY public.agv_map_roads DROP CONSTRAINT IF EXISTS agv_map_roads_pkey;
ALTER TABLE IF EXISTS ONLY public.agv_map_points DROP CONSTRAINT IF EXISTS agv_map_points_pkey;
ALTER TABLE IF EXISTS ONLY public.agv_map_points DROP CONSTRAINT IF EXISTS agv_map_points_map_id_name_id_key;
ALTER TABLE IF EXISTS ONLY public.agv_map_codes DROP CONSTRAINT IF EXISTS agv_map_codes_pkey;
ALTER TABLE IF EXISTS ONLY public.agv_map_codes DROP CONSTRAINT IF EXISTS agv_map_codes_map_id_code_id_key;
ALTER TABLE IF EXISTS ONLY public.agv_map_benziers DROP CONSTRAINT IF EXISTS agv_map_benziers_pkey;
ALTER TABLE IF EXISTS ONLY public.agv_integrations DROP CONSTRAINT IF EXISTS agv_integrations_pkey;
ALTER TABLE IF EXISTS ONLY public.agv_integrations DROP CONSTRAINT IF EXISTS agv_integrations_conn_id_key;
ALTER TABLE IF EXISTS ONLY public.agv_integration_logs DROP CONSTRAINT IF EXISTS agv_integration_logs_pkey;
ALTER TABLE IF EXISTS ONLY public.agv_devices DROP CONSTRAINT IF EXISTS agv_devices_pkey;
ALTER TABLE IF EXISTS public.agvs ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.agv_workflow_templates ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.agv_tasks ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.agv_task_executions ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.agv_map_roads ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.agv_map_points ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.agv_map_codes ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.agv_map_benziers ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.agv_integrations ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS public.agv_integration_logs ALTER COLUMN id DROP DEFAULT;
DROP SEQUENCE IF EXISTS public.agvs_id_seq;
DROP TABLE IF EXISTS public.agvs;
DROP SEQUENCE IF EXISTS public.agv_workflow_templates_id_seq;
DROP TABLE IF EXISTS public.agv_workflow_templates;
DROP SEQUENCE IF EXISTS public.agv_tasks_id_seq;
DROP TABLE IF EXISTS public.agv_tasks;
DROP SEQUENCE IF EXISTS public.agv_task_executions_id_seq;
DROP TABLE IF EXISTS public.agv_task_executions;
DROP TABLE IF EXISTS public.agv_schedules;
DROP TABLE IF EXISTS public.agv_maps;
DROP SEQUENCE IF EXISTS public.agv_map_roads_id_seq;
DROP TABLE IF EXISTS public.agv_map_roads;
DROP SEQUENCE IF EXISTS public.agv_map_points_id_seq;
DROP TABLE IF EXISTS public.agv_map_points;
DROP SEQUENCE IF EXISTS public.agv_map_codes_id_seq;
DROP TABLE IF EXISTS public.agv_map_codes;
DROP SEQUENCE IF EXISTS public.agv_map_benziers_id_seq;
DROP TABLE IF EXISTS public.agv_map_benziers;
DROP SEQUENCE IF EXISTS public.agv_integrations_id_seq;
DROP TABLE IF EXISTS public.agv_integrations;
DROP SEQUENCE IF EXISTS public.agv_integration_logs_id_seq;
DROP TABLE IF EXISTS public.agv_integration_logs;
DROP VIEW IF EXISTS public.agv_devices_live;
DROP TABLE IF EXISTS public.agv_devices;
DROP FUNCTION IF EXISTS public.update_updated_at_column();
DROP FUNCTION IF EXISTS public.set_updated_at();
--
-- Name: set_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
                BEGIN
                  NEW.updated_at = now();
                  RETURN NEW;
                END;
                $$;


--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.update_at = NOW();
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: agv_devices; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agv_devices (
    name text NOT NULL,
    agv_type text NOT NULL,
    ip inet,
    port integer,
    last_seen timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    map_id text,
    factory text,
    last_tag text,
    subnet text,
    gateway text,
    dns text,
    can_reverse boolean DEFAULT true
);


--
-- Name: agv_devices_live; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.agv_devices_live AS
 SELECT name,
    agv_type,
    ip,
    port,
    last_seen,
    created_at,
    updated_at,
        CASE
            WHEN ((last_seen IS NOT NULL) AND (last_seen >= (now() - '00:00:03'::interval))) THEN 'online'::text
            ELSE 'offline'::text
        END AS status
   FROM public.agv_devices d;


--
-- Name: agv_integration_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agv_integration_logs (
    id integer NOT NULL,
    conn_id character varying(36),
    direction character varying(10),
    event character varying(50),
    status_code integer,
    request_body text,
    response_body text,
    error_msg text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: agv_integration_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agv_integration_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agv_integration_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agv_integration_logs_id_seq OWNED BY public.agv_integration_logs.id;


--
-- Name: agv_integrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agv_integrations (
    id integer NOT NULL,
    conn_id character varying(36) DEFAULT (gen_random_uuid())::text NOT NULL,
    name character varying(200) NOT NULL,
    system_type character varying(50) DEFAULT 'generic'::character varying,
    direction character varying(20) DEFAULT 'both'::character varying,
    enabled boolean DEFAULT true,
    api_key character varying(128),
    map_id text,
    default_agv character varying(50),
    callback_url text,
    callback_auth_type character varying(20) DEFAULT 'bearer'::character varying,
    callback_auth_value text,
    callback_events text DEFAULT 'completed,failed,cancelled'::text,
    poll_enabled boolean DEFAULT false,
    poll_url text,
    poll_interval integer DEFAULT 60,
    poll_auth_type character varying(20) DEFAULT 'bearer'::character varying,
    poll_auth_value text,
    poll_field_map jsonb DEFAULT '{}'::jsonb,
    field_map jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: agv_integrations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agv_integrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agv_integrations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agv_integrations_id_seq OWNED BY public.agv_integrations.id;


--
-- Name: agv_map_benziers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agv_map_benziers (
    id integer NOT NULL,
    map_id text,
    name character varying(255),
    id_source character varying(50),
    id_dest character varying(50),
    point_start_x double precision,
    point_start_y double precision,
    point_end_x double precision,
    point_end_y double precision,
    curve_point_start_x double precision,
    curve_point_start_y double precision,
    curve_point_end_x double precision,
    curve_point_end_y double precision,
    width double precision DEFAULT 0.3,
    speed double precision DEFAULT 0.3,
    move_direction integer DEFAULT 0,
    lidar_off boolean DEFAULT false,
    lidar_off_dir text DEFAULT 'none'::text
);


--
-- Name: agv_map_benziers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agv_map_benziers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agv_map_benziers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agv_map_benziers_id_seq OWNED BY public.agv_map_benziers.id;


--
-- Name: agv_map_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agv_map_codes (
    id integer NOT NULL,
    map_id text,
    code_id integer NOT NULL,
    code text NOT NULL,
    x double precision NOT NULL,
    y double precision NOT NULL,
    theta double precision NOT NULL
);


--
-- Name: agv_map_codes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agv_map_codes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agv_map_codes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agv_map_codes_id_seq OWNED BY public.agv_map_codes.id;


--
-- Name: agv_map_points; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agv_map_points (
    id integer NOT NULL,
    map_id text,
    name_id text NOT NULL,
    name text,
    x double precision NOT NULL,
    y double precision NOT NULL,
    theta double precision NOT NULL,
    type integer DEFAULT 0,
    zone text,
    action jsonb,
    carrier integer DEFAULT 0,
    available boolean DEFAULT false,
    accuracy integer DEFAULT 0,
    speed double precision DEFAULT 0.5
);


--
-- Name: agv_map_points_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agv_map_points_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agv_map_points_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agv_map_points_id_seq OWNED BY public.agv_map_points.id;


--
-- Name: agv_map_roads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agv_map_roads (
    id integer NOT NULL,
    map_id text,
    name text,
    id_source text NOT NULL,
    id_dest text NOT NULL,
    point_start_x double precision NOT NULL,
    point_start_y double precision NOT NULL,
    point_end_x double precision NOT NULL,
    point_end_y double precision NOT NULL,
    width double precision DEFAULT 0.95,
    speed double precision DEFAULT 0.3,
    move_direction integer DEFAULT 0,
    distance double precision,
    lidar_off boolean DEFAULT false,
    lidar_off_dir text DEFAULT 'none'::text
);


--
-- Name: agv_map_roads_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agv_map_roads_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agv_map_roads_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agv_map_roads_id_seq OWNED BY public.agv_map_roads.id;


--
-- Name: agv_maps; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agv_maps (
    id text NOT NULL,
    name text NOT NULL,
    origin_x double precision DEFAULT 0 NOT NULL,
    origin_y double precision DEFAULT 0 NOT NULL,
    origin_theta double precision DEFAULT 0 NOT NULL,
    resolution double precision DEFAULT 0.05 NOT NULL,
    image_path text,
    modify_time timestamp with time zone,
    layer integer DEFAULT 0,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: agv_schedules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agv_schedules (
    id text NOT NULL,
    agv_id text NOT NULL,
    command text NOT NULL,
    team_id integer,
    priority integer DEFAULT 3,
    schedule_type text NOT NULL,
    scheduled_at timestamp with time zone,
    time_of_day text,
    days_of_week integer[],
    interval_minutes integer,
    label text DEFAULT ''::text,
    active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    last_run timestamp with time zone,
    next_run timestamp with time zone,
    run_count integer DEFAULT 0,
    map_id text
);


--
-- Name: agv_task_executions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agv_task_executions (
    id integer NOT NULL,
    cmd_id character varying(16) NOT NULL,
    agv_id character varying(50),
    command character varying(50),
    dest_node character varying(100),
    status character varying(20) DEFAULT 'queued'::character varying,
    queued_at timestamp with time zone DEFAULT now(),
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    notes text,
    session_id character varying(40),
    session_label character varying(200)
);


--
-- Name: agv_task_executions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agv_task_executions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agv_task_executions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agv_task_executions_id_seq OWNED BY public.agv_task_executions.id;


--
-- Name: agv_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agv_tasks (
    id integer NOT NULL,
    task_id character varying(36) DEFAULT (gen_random_uuid())::text,
    agv_id character varying(50) NOT NULL,
    destination character varying(50) NOT NULL,
    map_id character varying(50),
    status character varying(20) DEFAULT 'pending'::character varying,
    order_id character varying(100),
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    operator_name text,
    operator_id text,
    order_info jsonb
);


--
-- Name: agv_tasks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agv_tasks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agv_tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agv_tasks_id_seq OWNED BY public.agv_tasks.id;


--
-- Name: agv_workflow_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agv_workflow_templates (
    id integer NOT NULL,
    template_id character varying(36) DEFAULT (gen_random_uuid())::text,
    name character varying(200) NOT NULL,
    steps jsonb DEFAULT '[]'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: agv_workflow_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agv_workflow_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agv_workflow_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agv_workflow_templates_id_seq OWNED BY public.agv_workflow_templates.id;


--
-- Name: agvs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agvs (
    id integer NOT NULL,
    agv_id character varying(50) NOT NULL,
    serial_number character varying(50),
    manufacturer character varying(50) DEFAULT 'TNG:TOT'::character varying,
    model character varying(50),
    ip_address character varying(45),
    current_map character varying(50),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    is_online boolean DEFAULT true
);


--
-- Name: agvs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.agvs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: agvs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.agvs_id_seq OWNED BY public.agvs.id;


--
-- Name: agv_integration_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_integration_logs ALTER COLUMN id SET DEFAULT nextval('public.agv_integration_logs_id_seq'::regclass);


--
-- Name: agv_integrations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_integrations ALTER COLUMN id SET DEFAULT nextval('public.agv_integrations_id_seq'::regclass);


--
-- Name: agv_map_benziers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_map_benziers ALTER COLUMN id SET DEFAULT nextval('public.agv_map_benziers_id_seq'::regclass);


--
-- Name: agv_map_codes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_map_codes ALTER COLUMN id SET DEFAULT nextval('public.agv_map_codes_id_seq'::regclass);


--
-- Name: agv_map_points id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_map_points ALTER COLUMN id SET DEFAULT nextval('public.agv_map_points_id_seq'::regclass);


--
-- Name: agv_map_roads id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_map_roads ALTER COLUMN id SET DEFAULT nextval('public.agv_map_roads_id_seq'::regclass);


--
-- Name: agv_task_executions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_task_executions ALTER COLUMN id SET DEFAULT nextval('public.agv_task_executions_id_seq'::regclass);


--
-- Name: agv_tasks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_tasks ALTER COLUMN id SET DEFAULT nextval('public.agv_tasks_id_seq'::regclass);


--
-- Name: agv_workflow_templates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_workflow_templates ALTER COLUMN id SET DEFAULT nextval('public.agv_workflow_templates_id_seq'::regclass);


--
-- Name: agvs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agvs ALTER COLUMN id SET DEFAULT nextval('public.agvs_id_seq'::regclass);


--
-- Data for Name: agv_devices; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agv_devices (name, agv_type, ip, port, last_seen, created_at, updated_at, map_id, factory, last_tag, subnet, gateway, dns, can_reverse) FROM stdin;
AGV02	trailer	192.168.0.192	\N	2026-07-20 13:27:23.880582+07	2026-07-17 09:49:10.309446+07	2026-07-20 13:27:23.880582+07	1784004253436	Vonhai	10	255.255.255.0	192.168.0.1	8.8.8.8	f
\.


--
-- Data for Name: agv_integration_logs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agv_integration_logs (id, conn_id, direction, event, status_code, request_body, response_body, error_msg, created_at) FROM stdin;
1	640f3326-855c-4d95-afb0-1357448e8f4a	out	test	200	{"event": "test", "task_id": "test-c179ddc2", "agv_id": "AGV01", "destination": "99", "status": "completed", "timestamp": "2026-06-22T14:37:49", "message": "Test t\\u1eeb AGV server \\u2014 k\\u1ebft n\\u1ed1i 'WMS TOT'"}	<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="/_nuxt/entry.CmXsnl3c.css" crossorigin><link rel="modulepreload" as="script" crossorigin href="/_nuxt/jw9M8EJW.js"><script type="module" src="/_nuxt/jw9M8EJW.js" crossorigin></script><script>"use strict";(()=>{const t=window,e=document.documentElement,c=["dark","light"],n=getStorageValue("localStorage","nuxt-color-mode")||"light";let i=n==="system"?u()		2026-06-22 14:37:49.674825+07
\.


--
-- Data for Name: agv_integrations; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agv_integrations (id, conn_id, name, system_type, direction, enabled, api_key, map_id, default_agv, callback_url, callback_auth_type, callback_auth_value, callback_events, poll_enabled, poll_url, poll_interval, poll_auth_type, poll_auth_value, poll_field_map, field_map, created_at, updated_at) FROM stdin;
1	640f3326-855c-4d95-afb0-1357448e8f4a	WMS TOT	wms	both	f	93b4117ba7cc43bba90ae9b50df5d4b9	\N	AGV01	https://iot.tot360.com.vn	none	\N	failed	f	\N	60	bearer	\N	{}	{}	2026-06-22 14:23:12.810087+07	2026-06-22 14:23:12.810087+07
\.


--
-- Data for Name: agv_map_benziers; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agv_map_benziers (id, map_id, name, id_source, id_dest, point_start_x, point_start_y, point_end_x, point_end_y, curve_point_start_x, curve_point_start_y, curve_point_end_x, curve_point_end_y, width, speed, move_direction, lidar_off, lidar_off_dir) FROM stdin;
1	56		3	4	-1.9831966161727905	-8.290040016174316	0.6464591026306152	-6.204639434814453	0.4639039999966116	-8.483669333322771	-1.0720960000033883	-6.691669333322773	0.3	0.3	0	f	none
2	56		5	4	4.985492706298828	-6.010046482086182	0.6464591026306152	-6.204639434814453	2.561102750751498	-3.4374298777402177	3.414436084084831	-9.784096544406886	0.95	0.3	0	f	none
5	98		2	3	-16.930097579956055	17.904834747314453	-15.251384735107422	20.00648333231608	-17.23055140177409	19.121066665649415	-17.07430140177409	20.110649998982748	0.95	0.3	0	f	none
6	98		3	2	-15.251384735107422	20.00648333231608	-16.930097579956055	17.904834747314453	-16.91805140177409	20.110649998982748	-17.334718068440754	18.912733332316076	0.95	0.3	0	f	none
7	98		3	5	-15.251384735107422	20.00648333231608	-11.468180338541668	18.08467025756836	-15.534847005208334	17.41800359090169	-12.334847005208335	18.21800359090169	0.95	0.3	0	f	none
8	98		5	3	-11.468180338541668	18.08467025756836	-15.251384735107422	20.00648333231608	-13.134847005208336	18.08467025756836	-15.36818033854167	17.518003590901692	0.95	0.3	0	f	none
144	1784004253436		22	12	195	155	245	235	226	175	243	201	0.95	0.3	0	f	none
145	1784004253436		13	14	245	344	285	475	244	410	257	454	0.95	0.3	1	f	none
146	1784004253436		201	13	365	396	245	344	309	389	269	372	0.95	0.3	1	f	none
36	59		1	2	10.82258129119873	-2.29671311378479	10.106666666666666	-0.06791666666667028	11.09333333333333	-0.6812500000000029	10.959999999999999	0.19874999999999832	0.3	0.3	0	f	none
37	59		3	1	7.2799999999999985	-1.1879166666666692	10.82258129119873	-2.29671311378479	9.33333333333333	-0.8945833333333355	10.959999999999999	-0.2279166666666697	0.3	0.3	0	f	none
38	59		2	1	10.106666666666666	-0.06791666666667028	10.82258129119873	-2.29671311378479	10.891950000000001	0.11638750000000186	11.165016666666666	-0.7710791666666665	0.3	0.3	0	f	none
39	99		5	6	17.829244613647457	-7.077150090535475	22.95619773864746	-12.285483423868811	17.78855450948079	-12.244793319702143	19.13132794698079	-12.041342798868811	0.925	0.5	0	f	none
40	99		6	5	22.95619773864746	-12.285483423868811	17.829244613647457	-7.077150090535475	19.78236961364746	-12.285483423868811	17.66648419698079	-12.204103215535476	0.9	0.5	0	f	none
41	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		16	19	16.618	13.269	16.262	3.731	0	0	0	0	0.95	0.3	0	f	none
42	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		19	16	16.262	3.731	16.618	13.269	0	0	0	0	0.95	0.3	0	f	none
53	1779790224391		16	4	240	-85	-17	-4	161	-41	76	-14	0.95	0.4	0	f	none
\.


--
-- Data for Name: agv_map_codes; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agv_map_codes (id, map_id, code_id, code, x, y, theta) FROM stdin;
6	87	1061	10	-7.79447842	11.9107866	1.50792599
7	87	1066	11	-7.89637661	11.7518492	-0.0706715435
8	87	1068	27	-14.2355404	8.90089035	-0.0210229736
9	87	1069	31	-14.3102102	6.48361063	-1.61518478
10	87	1071	29	-14.3704729	3.41753626	-0.00481918128
11	87	1072	25	-14.593421	0.193691015	3.09035516
12	87	1077	26	-14.6250782	-7.99952316	0.0188865718
13	87	1075	28	-14.6630859	-5.69285059	0.0250774305
14	87	1074	30	-14.8354807	-3.52513814	-3.06226039
20	99	1097	000000XY001000	14.2483654	0.829822302	3.1003263
21	99	1099	13	6.01754665	0.552490711	3.10138583
22	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	1	1	7.021	10.01	0
23	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	10	10	3.999	15.787	0
24	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	11	11	6.784	14.809	0
25	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	12	12	3.199	13.328	0
26	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	13	13	18.691	13.417	0
27	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	14	14	21.12	10.455	0
28	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	15	15	19.758	8.026	0
29	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	16	16	16.618	13.269	0
30	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	17	17	12.678	15.49	0
31	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	18	18	11.612	3.879	0
32	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	19	19	16.262	3.731	0
33	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	2	2	11.167	13.061	0
34	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	20	20	21.861	4.205	0
35	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	21	21	4.177	4.708	0
36	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	22	22	3.051	8.144	0
37	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	23	23	12.797	7.493	0
38	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	24	24	10.111	7.978	0
39	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	25	25	20.094	19.948	0
40	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	26	26	24.678	13.225	0
41	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	27	27	25.086	7.112	0
42	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	28	28	39.972	17.083	0
43	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	3	3	11.049	17.149	0
44	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	4	4	15.077	17.653	0
45	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	5	5	18.128	15.224	0
46	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	6	6	18.04	19.933	0
47	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	7	7	10.486	19.637	0
48	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	8	8	6.961	18.452	0
49	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	9	9	5.184	21.029	0
50	4001ae10-9a25-4f79-9941-6bfc467df987	1	1	2	2	0
51	4001ae10-9a25-4f79-9941-6bfc467df987	10	10	18	6	0
52	4001ae10-9a25-4f79-9941-6bfc467df987	11	11	2	10	0
53	4001ae10-9a25-4f79-9941-6bfc467df987	12	12	6	10	0
54	4001ae10-9a25-4f79-9941-6bfc467df987	13	13	10	10	0
55	4001ae10-9a25-4f79-9941-6bfc467df987	14	14	14	10	0
56	4001ae10-9a25-4f79-9941-6bfc467df987	15	15	18	10	0
57	4001ae10-9a25-4f79-9941-6bfc467df987	16	16	10	6	0
58	4001ae10-9a25-4f79-9941-6bfc467df987	17	17	14	6	0
59	4001ae10-9a25-4f79-9941-6bfc467df987	18	18	10	10	0
60	4001ae10-9a25-4f79-9941-6bfc467df987	19	19	14	10	0
61	4001ae10-9a25-4f79-9941-6bfc467df987	2	2	6	2	0
62	4001ae10-9a25-4f79-9941-6bfc467df987	20	20	18	10	0
63	4001ae10-9a25-4f79-9941-6bfc467df987	3	3	10	2	0
64	4001ae10-9a25-4f79-9941-6bfc467df987	4	4	14	2	0
65	4001ae10-9a25-4f79-9941-6bfc467df987	5	5	18	2	0
66	4001ae10-9a25-4f79-9941-6bfc467df987	6	6	2	6	0
67	4001ae10-9a25-4f79-9941-6bfc467df987	7	7	6	6	0
68	4001ae10-9a25-4f79-9941-6bfc467df987	8	8	10	6	0
69	4001ae10-9a25-4f79-9941-6bfc467df987	9	9	14	6	0
70	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	1	1	2	2	0
71	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	10	10	18	6	0
72	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	11	11	2	10	0
73	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	12	12	6	10	0
74	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	13	13	10	10	0
75	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	14	14	14	10	0
76	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	15	15	18	10	0
77	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	16	16	10	6	0
78	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	17	17	14	6	0
79	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	18	18	10	10	0
80	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	19	19	14	10	0
81	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	2	2	6	2	0
82	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	20	20	18	10	0
83	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	3	3	10	2	0
84	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	4	4	14	2	0
85	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	5	5	18	2	0
86	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	6	6	2	6	0
87	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	7	7	6	6	0
88	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	8	8	10	6	0
89	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	9	9	14	6	0
90	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	1	1	2	2	0
91	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	10	10	18	6	0
92	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	11	11	2	10	0
93	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	12	12	6	10	0
94	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	13	13	10	10	0
95	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	14	14	14	10	0
96	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	15	15	18	10	0
97	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	16	16	10	6	0
98	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	17	17	14	6	0
99	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	18	18	10	10	0
100	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	19	19	14	10	0
101	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	2	2	6	2	0
102	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	20	20	18	10	0
103	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	3	3	10	2	0
104	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	4	4	14	2	0
105	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	5	5	18	2	0
106	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	6	6	2	6	0
107	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	7	7	6	6	0
108	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	8	8	10	6	0
109	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	9	9	14	6	0
110	4656f23b-ed40-43d1-a314-94bbdedf5d29	1	1	2	2	0
111	4656f23b-ed40-43d1-a314-94bbdedf5d29	10	10	18	6	0
112	4656f23b-ed40-43d1-a314-94bbdedf5d29	11	11	2	10	0
113	4656f23b-ed40-43d1-a314-94bbdedf5d29	12	12	6	10	0
114	4656f23b-ed40-43d1-a314-94bbdedf5d29	13	13	10	10	0
115	4656f23b-ed40-43d1-a314-94bbdedf5d29	14	14	14	10	0
116	4656f23b-ed40-43d1-a314-94bbdedf5d29	15	15	18	10	0
117	4656f23b-ed40-43d1-a314-94bbdedf5d29	16	16	10	6	0
118	4656f23b-ed40-43d1-a314-94bbdedf5d29	17	17	14	6	0
119	4656f23b-ed40-43d1-a314-94bbdedf5d29	18	18	10	10	0
120	4656f23b-ed40-43d1-a314-94bbdedf5d29	19	19	14	10	0
121	4656f23b-ed40-43d1-a314-94bbdedf5d29	2	2	6	2	0
122	4656f23b-ed40-43d1-a314-94bbdedf5d29	20	20	18	10	0
123	4656f23b-ed40-43d1-a314-94bbdedf5d29	3	3	10	2	0
124	4656f23b-ed40-43d1-a314-94bbdedf5d29	4	4	14	2	0
125	4656f23b-ed40-43d1-a314-94bbdedf5d29	5	5	18	2	0
126	4656f23b-ed40-43d1-a314-94bbdedf5d29	6	6	2	6	0
127	4656f23b-ed40-43d1-a314-94bbdedf5d29	7	7	6	6	0
128	4656f23b-ed40-43d1-a314-94bbdedf5d29	8	8	10	6	0
129	4656f23b-ed40-43d1-a314-94bbdedf5d29	9	9	14	6	0
130	ceed0bd3-7f76-46e4-b188-61010dcd100a	1	1	2	2	0
131	ceed0bd3-7f76-46e4-b188-61010dcd100a	10	10	18	6	0
132	ceed0bd3-7f76-46e4-b188-61010dcd100a	11	11	2	10	0
133	ceed0bd3-7f76-46e4-b188-61010dcd100a	12	12	6	10	0
134	ceed0bd3-7f76-46e4-b188-61010dcd100a	13	13	10	10	0
135	ceed0bd3-7f76-46e4-b188-61010dcd100a	14	14	14	10	0
136	ceed0bd3-7f76-46e4-b188-61010dcd100a	15	15	18	10	0
137	ceed0bd3-7f76-46e4-b188-61010dcd100a	16	16	10	6	0
138	ceed0bd3-7f76-46e4-b188-61010dcd100a	17	17	14	6	0
139	ceed0bd3-7f76-46e4-b188-61010dcd100a	18	18	10	10	0
140	ceed0bd3-7f76-46e4-b188-61010dcd100a	19	19	14	10	0
141	ceed0bd3-7f76-46e4-b188-61010dcd100a	2	2	6	2	0
142	ceed0bd3-7f76-46e4-b188-61010dcd100a	20	20	18	10	0
143	ceed0bd3-7f76-46e4-b188-61010dcd100a	3	3	10	2	0
144	ceed0bd3-7f76-46e4-b188-61010dcd100a	4	4	14	2	0
145	ceed0bd3-7f76-46e4-b188-61010dcd100a	5	5	18	2	0
146	ceed0bd3-7f76-46e4-b188-61010dcd100a	6	6	2	6	0
147	ceed0bd3-7f76-46e4-b188-61010dcd100a	7	7	6	6	0
148	ceed0bd3-7f76-46e4-b188-61010dcd100a	8	8	10	6	0
149	ceed0bd3-7f76-46e4-b188-61010dcd100a	9	9	14	6	0
150	98162503-c3c3-452f-a896-e85ded516cb9	1	1	2	2	0
151	98162503-c3c3-452f-a896-e85ded516cb9	10	10	18	6	0
152	98162503-c3c3-452f-a896-e85ded516cb9	11	11	2	10	0
153	98162503-c3c3-452f-a896-e85ded516cb9	12	12	6	10	0
154	98162503-c3c3-452f-a896-e85ded516cb9	13	13	10	10	0
155	98162503-c3c3-452f-a896-e85ded516cb9	14	14	14	10	0
156	98162503-c3c3-452f-a896-e85ded516cb9	15	15	18	10	0
157	98162503-c3c3-452f-a896-e85ded516cb9	16	16	10	6	0
158	98162503-c3c3-452f-a896-e85ded516cb9	17	17	14	6	0
159	98162503-c3c3-452f-a896-e85ded516cb9	18	18	10	10	0
160	98162503-c3c3-452f-a896-e85ded516cb9	19	19	14	10	0
161	98162503-c3c3-452f-a896-e85ded516cb9	2	2	6	2	0
162	98162503-c3c3-452f-a896-e85ded516cb9	20	20	18	10	0
163	98162503-c3c3-452f-a896-e85ded516cb9	3	3	10	2	0
164	98162503-c3c3-452f-a896-e85ded516cb9	4	4	14	2	0
165	98162503-c3c3-452f-a896-e85ded516cb9	5	5	18	2	0
166	98162503-c3c3-452f-a896-e85ded516cb9	6	6	2	6	0
167	98162503-c3c3-452f-a896-e85ded516cb9	7	7	6	6	0
168	98162503-c3c3-452f-a896-e85ded516cb9	8	8	10	6	0
169	98162503-c3c3-452f-a896-e85ded516cb9	9	9	14	6	0
170	b6fcdc48-990f-4dfd-a50e-2eabca664196	1	1	2	2	0
171	b6fcdc48-990f-4dfd-a50e-2eabca664196	10	10	18	6	0
172	b6fcdc48-990f-4dfd-a50e-2eabca664196	11	11	2	10	0
173	b6fcdc48-990f-4dfd-a50e-2eabca664196	12	12	6	10	0
174	b6fcdc48-990f-4dfd-a50e-2eabca664196	13	13	10	10	0
175	b6fcdc48-990f-4dfd-a50e-2eabca664196	14	14	14	10	0
176	b6fcdc48-990f-4dfd-a50e-2eabca664196	15	15	18	10	0
177	b6fcdc48-990f-4dfd-a50e-2eabca664196	16	16	10	6	0
178	b6fcdc48-990f-4dfd-a50e-2eabca664196	17	17	14	6	0
179	b6fcdc48-990f-4dfd-a50e-2eabca664196	18	18	10	10	0
180	b6fcdc48-990f-4dfd-a50e-2eabca664196	19	19	14	10	0
181	b6fcdc48-990f-4dfd-a50e-2eabca664196	2	2	6	2	0
182	b6fcdc48-990f-4dfd-a50e-2eabca664196	20	20	18	10	0
183	b6fcdc48-990f-4dfd-a50e-2eabca664196	3	3	10	2	0
184	b6fcdc48-990f-4dfd-a50e-2eabca664196	4	4	14	2	0
185	b6fcdc48-990f-4dfd-a50e-2eabca664196	5	5	18	2	0
186	b6fcdc48-990f-4dfd-a50e-2eabca664196	6	6	2	6	0
187	b6fcdc48-990f-4dfd-a50e-2eabca664196	7	7	6	6	0
188	b6fcdc48-990f-4dfd-a50e-2eabca664196	8	8	10	6	0
189	b6fcdc48-990f-4dfd-a50e-2eabca664196	9	9	14	6	0
190	61d76858-93a2-413d-9840-ea136908c9ab	1	1	2	2	0
191	61d76858-93a2-413d-9840-ea136908c9ab	10	10	18	6	0
192	61d76858-93a2-413d-9840-ea136908c9ab	11	11	2	10	0
193	61d76858-93a2-413d-9840-ea136908c9ab	12	12	6	10	0
194	61d76858-93a2-413d-9840-ea136908c9ab	13	13	10	10	0
195	61d76858-93a2-413d-9840-ea136908c9ab	14	14	14	10	0
196	61d76858-93a2-413d-9840-ea136908c9ab	15	15	18	10	0
197	61d76858-93a2-413d-9840-ea136908c9ab	16	16	10	6	0
198	61d76858-93a2-413d-9840-ea136908c9ab	17	17	14	6	0
199	61d76858-93a2-413d-9840-ea136908c9ab	18	18	10	10	0
200	61d76858-93a2-413d-9840-ea136908c9ab	19	19	14	10	0
201	61d76858-93a2-413d-9840-ea136908c9ab	2	2	6	2	0
202	61d76858-93a2-413d-9840-ea136908c9ab	20	20	18	10	0
203	61d76858-93a2-413d-9840-ea136908c9ab	3	3	10	2	0
204	61d76858-93a2-413d-9840-ea136908c9ab	4	4	14	2	0
205	61d76858-93a2-413d-9840-ea136908c9ab	5	5	18	2	0
206	61d76858-93a2-413d-9840-ea136908c9ab	6	6	2	6	0
207	61d76858-93a2-413d-9840-ea136908c9ab	7	7	6	6	0
208	61d76858-93a2-413d-9840-ea136908c9ab	8	8	10	6	0
209	61d76858-93a2-413d-9840-ea136908c9ab	9	9	14	6	0
210	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	1	1	2	2	0
211	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	10	10	18	6	0
212	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	11	11	2	10	0
213	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	12	12	6	10	0
214	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	13	13	10	10	0
215	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	14	14	14	10	0
216	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	15	15	18	10	0
217	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	16	16	10	6	0
218	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	17	17	14	6	0
219	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	18	18	10	10	0
220	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	19	19	14	10	0
221	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	2	2	6	2	0
222	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	20	20	18	10	0
223	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	3	3	10	2	0
224	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	4	4	14	2	0
225	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	5	5	18	2	0
226	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	6	6	2	6	0
227	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	7	7	6	6	0
228	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	8	8	10	6	0
229	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	9	9	14	6	0
230	88173d83-9aa6-4df1-aaa8-c06b63569fc5	1	1	2	2	0
231	88173d83-9aa6-4df1-aaa8-c06b63569fc5	10	10	18	6	0
232	88173d83-9aa6-4df1-aaa8-c06b63569fc5	11	11	2	10	0
233	88173d83-9aa6-4df1-aaa8-c06b63569fc5	12	12	6	10	0
234	88173d83-9aa6-4df1-aaa8-c06b63569fc5	13	13	10	10	0
235	88173d83-9aa6-4df1-aaa8-c06b63569fc5	14	14	14	10	0
236	88173d83-9aa6-4df1-aaa8-c06b63569fc5	15	15	18	10	0
237	88173d83-9aa6-4df1-aaa8-c06b63569fc5	16	16	10	6	0
238	88173d83-9aa6-4df1-aaa8-c06b63569fc5	17	17	14	6	0
239	88173d83-9aa6-4df1-aaa8-c06b63569fc5	18	18	10	10	0
240	88173d83-9aa6-4df1-aaa8-c06b63569fc5	19	19	14	10	0
241	88173d83-9aa6-4df1-aaa8-c06b63569fc5	2	2	6	2	0
242	88173d83-9aa6-4df1-aaa8-c06b63569fc5	20	20	18	10	0
243	88173d83-9aa6-4df1-aaa8-c06b63569fc5	3	3	10	2	0
244	88173d83-9aa6-4df1-aaa8-c06b63569fc5	4	4	14	2	0
245	88173d83-9aa6-4df1-aaa8-c06b63569fc5	5	5	18	2	0
246	88173d83-9aa6-4df1-aaa8-c06b63569fc5	6	6	2	6	0
247	88173d83-9aa6-4df1-aaa8-c06b63569fc5	7	7	6	6	0
248	88173d83-9aa6-4df1-aaa8-c06b63569fc5	8	8	10	6	0
249	88173d83-9aa6-4df1-aaa8-c06b63569fc5	9	9	14	6	0
250	b7badbae-9aaf-4f4a-9ed0-87096255212c	1	1	2	2	0
251	b7badbae-9aaf-4f4a-9ed0-87096255212c	10	10	18	6	0
252	b7badbae-9aaf-4f4a-9ed0-87096255212c	11	11	2	10	0
253	b7badbae-9aaf-4f4a-9ed0-87096255212c	12	12	6	10	0
254	b7badbae-9aaf-4f4a-9ed0-87096255212c	13	13	10	10	0
255	b7badbae-9aaf-4f4a-9ed0-87096255212c	14	14	14	10	0
256	b7badbae-9aaf-4f4a-9ed0-87096255212c	15	15	18	10	0
257	b7badbae-9aaf-4f4a-9ed0-87096255212c	16	16	10	6	0
258	b7badbae-9aaf-4f4a-9ed0-87096255212c	17	17	14	6	0
259	b7badbae-9aaf-4f4a-9ed0-87096255212c	18	18	10	10	0
260	b7badbae-9aaf-4f4a-9ed0-87096255212c	19	19	14	10	0
261	b7badbae-9aaf-4f4a-9ed0-87096255212c	2	2	6	2	0
262	b7badbae-9aaf-4f4a-9ed0-87096255212c	20	20	18	10	0
263	b7badbae-9aaf-4f4a-9ed0-87096255212c	3	3	10	2	0
264	b7badbae-9aaf-4f4a-9ed0-87096255212c	4	4	14	2	0
265	b7badbae-9aaf-4f4a-9ed0-87096255212c	5	5	18	2	0
266	b7badbae-9aaf-4f4a-9ed0-87096255212c	6	6	2	6	0
267	b7badbae-9aaf-4f4a-9ed0-87096255212c	7	7	6	6	0
268	b7badbae-9aaf-4f4a-9ed0-87096255212c	8	8	10	6	0
269	b7badbae-9aaf-4f4a-9ed0-87096255212c	9	9	14	6	0
270	3772fe6a-6a43-4c30-a40e-125ddc5598c4	1	1	2	2	0
271	3772fe6a-6a43-4c30-a40e-125ddc5598c4	10	10	18	6	0
272	3772fe6a-6a43-4c30-a40e-125ddc5598c4	11	11	2	10	0
273	3772fe6a-6a43-4c30-a40e-125ddc5598c4	12	12	6	10	0
274	3772fe6a-6a43-4c30-a40e-125ddc5598c4	13	13	10	10	0
275	3772fe6a-6a43-4c30-a40e-125ddc5598c4	14	14	14	10	0
276	3772fe6a-6a43-4c30-a40e-125ddc5598c4	15	15	18	10	0
277	3772fe6a-6a43-4c30-a40e-125ddc5598c4	16	16	10	6	0
278	3772fe6a-6a43-4c30-a40e-125ddc5598c4	17	17	14	6	0
279	3772fe6a-6a43-4c30-a40e-125ddc5598c4	18	18	10	10	0
280	3772fe6a-6a43-4c30-a40e-125ddc5598c4	19	19	14	10	0
281	3772fe6a-6a43-4c30-a40e-125ddc5598c4	2	2	6	2	0
282	3772fe6a-6a43-4c30-a40e-125ddc5598c4	20	20	18	10	0
283	3772fe6a-6a43-4c30-a40e-125ddc5598c4	3	3	10	2	0
284	3772fe6a-6a43-4c30-a40e-125ddc5598c4	4	4	14	2	0
285	3772fe6a-6a43-4c30-a40e-125ddc5598c4	5	5	18	2	0
286	3772fe6a-6a43-4c30-a40e-125ddc5598c4	6	6	2	6	0
287	3772fe6a-6a43-4c30-a40e-125ddc5598c4	7	7	6	6	0
288	3772fe6a-6a43-4c30-a40e-125ddc5598c4	8	8	10	6	0
289	3772fe6a-6a43-4c30-a40e-125ddc5598c4	9	9	14	6	0
290	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	1	1	2	2	0
291	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	10	10	18	6	0
292	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	11	11	2	10	0
293	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	12	12	6	10	0
294	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	13	13	10	10	0
295	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	14	14	14	10	0
296	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	15	15	18	10	0
297	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	16	16	10	6	0
298	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	17	17	14	6	0
299	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	18	18	10	10	0
300	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	19	19	14	10	0
301	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	2	2	6	2	0
302	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	20	20	18	10	0
303	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	3	3	10	2	0
304	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	4	4	14	2	0
305	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	5	5	18	2	0
306	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	6	6	2	6	0
307	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	7	7	6	6	0
308	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	8	8	10	6	0
309	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	9	9	14	6	0
310	523fb5c2-e610-4f58-b471-646e295b8f15	1	1	2.037037037037037	11.981481481481481	0
311	523fb5c2-e610-4f58-b471-646e295b8f15	10	10	4.925925925925926	4.018518518518518	0
312	523fb5c2-e610-4f58-b471-646e295b8f15	11	11	8	12	0
313	523fb5c2-e610-4f58-b471-646e295b8f15	12	12	7.981481481481482	10.055555555555555	0
314	523fb5c2-e610-4f58-b471-646e295b8f15	13	13	7.907407407407407	8.055555555555555	0
315	523fb5c2-e610-4f58-b471-646e295b8f15	14	14	7.981481481481482	6.037037037037037	0
316	523fb5c2-e610-4f58-b471-646e295b8f15	15	15	8	4	0
317	523fb5c2-e610-4f58-b471-646e295b8f15	16	16	10.981481481481481	4	0
318	523fb5c2-e610-4f58-b471-646e295b8f15	17	17	11.037037037037036	6	0
319	523fb5c2-e610-4f58-b471-646e295b8f15	18	18	11.037037037037036	8	0
320	523fb5c2-e610-4f58-b471-646e295b8f15	19	19	10.944444444444445	9.88888888888889	0
321	523fb5c2-e610-4f58-b471-646e295b8f15	2	2	1.9814814814814814	9.981481481481481	0
322	523fb5c2-e610-4f58-b471-646e295b8f15	20	20	10.925925925925926	11.962962962962964	0
323	523fb5c2-e610-4f58-b471-646e295b8f15	21	21	14.962962962962964	12	0
324	523fb5c2-e610-4f58-b471-646e295b8f15	22	22	13.962962962962964	10.074074074074074	0
325	523fb5c2-e610-4f58-b471-646e295b8f15	23	23	13.851851851851851	7.2407407407407405	0
326	523fb5c2-e610-4f58-b471-646e295b8f15	24	24	14.648148148148149	5.111111111111111	0
327	523fb5c2-e610-4f58-b471-646e295b8f15	25	25	17.09259259259259	3.9074074074074066	0
328	523fb5c2-e610-4f58-b471-646e295b8f15	26	26	17.11111111111111	7.462962962962963	0
329	523fb5c2-e610-4f58-b471-646e295b8f15	27	27	16.574074074074073	10.055555555555555	0
330	523fb5c2-e610-4f58-b471-646e295b8f15	3	3	1.9814814814814814	8	0
331	523fb5c2-e610-4f58-b471-646e295b8f15	4	4	2	5.981481481481482	0
332	523fb5c2-e610-4f58-b471-646e295b8f15	5	5	1.962962962962963	3.9259259259259256	0
333	523fb5c2-e610-4f58-b471-646e295b8f15	6	6	5	11.981481481481481	0
334	523fb5c2-e610-4f58-b471-646e295b8f15	7	7	4.981481481481482	10	0
335	523fb5c2-e610-4f58-b471-646e295b8f15	8	8	4.981481481481482	8	0
336	523fb5c2-e610-4f58-b471-646e295b8f15	9	9	4.981481481481482	6.037037037037037	0
337	93e3ba66-0f9a-4267-95a1-71872f181779	1	1	1.9462962962962969	1.942592592592593	0
338	93e3ba66-0f9a-4267-95a1-71872f181779	10	10	17.961111111111112	13.911111111111111	0
339	93e3ba66-0f9a-4267-95a1-71872f181779	11	11	9.911111111111111	13.996296296296297	0
340	93e3ba66-0f9a-4267-95a1-71872f181779	12	12	2.2018518518518526	14.081481481481482	0
341	93e3ba66-0f9a-4267-95a1-71872f181779	13	13	2.074074074074075	18.085185185185185	0
342	93e3ba66-0f9a-4267-95a1-71872f181779	14	14	9.953703703703704	18.085185185185185	0
343	93e3ba66-0f9a-4267-95a1-71872f181779	15	15	17.833333333333332	17.914814814814815	0
344	93e3ba66-0f9a-4267-95a1-71872f181779	16	16	24.05185185185185	15.912962962962963	0
345	93e3ba66-0f9a-4267-95a1-71872f181779	17	17	24.009259259259256	8.331481481481482	0
346	93e3ba66-0f9a-4267-95a1-71872f181779	18	18	23.966666666666665	3.901851851851852	0
347	93e3ba66-0f9a-4267-95a1-71872f181779	19	19	24.09444444444444	12.122222222222224	0
348	93e3ba66-0f9a-4267-95a1-71872f181779	2	2	9.953703703703704	1.9851851851851876	0
349	93e3ba66-0f9a-4267-95a1-71872f181779	20	20	29.929629629629627	13.996296296296297	0
350	93e3ba66-0f9a-4267-95a1-71872f181779	21	21	30.014814814814812	9.992592592592594	0
351	93e3ba66-0f9a-4267-95a1-71872f181779	22	22	29.972222222222218	6.329629629629631	0
352	93e3ba66-0f9a-4267-95a1-71872f181779	23	23	35.89259259259259	9.907407407407408	0
353	93e3ba66-0f9a-4267-95a1-71872f181779	3	3	18.003703703703703	1.9851851851851876	0
354	93e3ba66-0f9a-4267-95a1-71872f181779	4	4	17.918518518518518	6.031481481481482	0
355	93e3ba66-0f9a-4267-95a1-71872f181779	5	5	10.081481481481482	6.116666666666667	0
356	93e3ba66-0f9a-4267-95a1-71872f181779	6	6	2.15925925925926	6.031481481481482	0
357	93e3ba66-0f9a-4267-95a1-71872f181779	7	7	1.9462962962962969	9.907407407407408	0
358	93e3ba66-0f9a-4267-95a1-71872f181779	8	8	9.996296296296297	9.822222222222223	0
359	93e3ba66-0f9a-4267-95a1-71872f181779	9	9	18.003703703703703	9.992592592592594	0
360	d2c251b5-9798-40c9-af25-0a8ec2f24833	1	1	1.9462962962962969	1.942592592592593	0
361	d2c251b5-9798-40c9-af25-0a8ec2f24833	10	10	17.961111111111112	13.911111111111111	0
362	d2c251b5-9798-40c9-af25-0a8ec2f24833	11	11	9.911111111111111	13.996296296296297	0
363	d2c251b5-9798-40c9-af25-0a8ec2f24833	12	12	2.2018518518518526	14.081481481481482	0
364	d2c251b5-9798-40c9-af25-0a8ec2f24833	13	13	2.074074074074075	18.085185185185185	0
365	d2c251b5-9798-40c9-af25-0a8ec2f24833	14	14	9.953703703703704	18.085185185185185	0
366	d2c251b5-9798-40c9-af25-0a8ec2f24833	15	15	17.833333333333332	17.914814814814815	0
367	d2c251b5-9798-40c9-af25-0a8ec2f24833	16	16	24.05185185185185	15.912962962962963	0
368	d2c251b5-9798-40c9-af25-0a8ec2f24833	17	17	24.009259259259256	8.331481481481482	0
369	d2c251b5-9798-40c9-af25-0a8ec2f24833	18	18	23.966666666666665	3.901851851851852	0
370	d2c251b5-9798-40c9-af25-0a8ec2f24833	19	19	24.09444444444444	12.122222222222224	0
371	d2c251b5-9798-40c9-af25-0a8ec2f24833	2	2	9.953703703703704	1.9851851851851876	0
372	d2c251b5-9798-40c9-af25-0a8ec2f24833	20	20	29.929629629629627	13.996296296296297	0
373	d2c251b5-9798-40c9-af25-0a8ec2f24833	21	21	30.014814814814812	9.992592592592594	0
374	d2c251b5-9798-40c9-af25-0a8ec2f24833	22	22	29.972222222222218	6.329629629629631	0
375	d2c251b5-9798-40c9-af25-0a8ec2f24833	23	23	35.89259259259259	9.907407407407408	0
376	d2c251b5-9798-40c9-af25-0a8ec2f24833	3	3	18.003703703703703	1.9851851851851876	0
377	d2c251b5-9798-40c9-af25-0a8ec2f24833	4	4	17.918518518518518	6.031481481481482	0
378	d2c251b5-9798-40c9-af25-0a8ec2f24833	5	5	10.081481481481482	6.116666666666667	0
379	d2c251b5-9798-40c9-af25-0a8ec2f24833	6	6	2.15925925925926	6.031481481481482	0
380	d2c251b5-9798-40c9-af25-0a8ec2f24833	7	7	1.9462962962962969	9.907407407407408	0
381	d2c251b5-9798-40c9-af25-0a8ec2f24833	8	8	9.996296296296297	9.822222222222223	0
382	d2c251b5-9798-40c9-af25-0a8ec2f24833	9	9	18.003703703703703	9.992592592592594	0
383	bb0dae6d-91cc-417d-9493-08beebeec142	1	1	1.946	1.943	0
384	bb0dae6d-91cc-417d-9493-08beebeec142	10	10	17.961	13.911	0
385	bb0dae6d-91cc-417d-9493-08beebeec142	11	11	9.911	13.996	0
386	bb0dae6d-91cc-417d-9493-08beebeec142	12	12	2.202	14.081	0
387	bb0dae6d-91cc-417d-9493-08beebeec142	13	13	2.074	18.085	0
388	bb0dae6d-91cc-417d-9493-08beebeec142	14	14	9.954	18.085	0
389	bb0dae6d-91cc-417d-9493-08beebeec142	15	15	17.833	17.915	0
390	bb0dae6d-91cc-417d-9493-08beebeec142	16	16	24.052	15.913	0
391	bb0dae6d-91cc-417d-9493-08beebeec142	17	17	24.009	8.331	0
392	bb0dae6d-91cc-417d-9493-08beebeec142	18	18	23.967	3.902	0
393	bb0dae6d-91cc-417d-9493-08beebeec142	19	19	24.094	12.122	0
394	bb0dae6d-91cc-417d-9493-08beebeec142	2	2	9.954	1.985	0
395	bb0dae6d-91cc-417d-9493-08beebeec142	20	20	29.93	13.996	0
396	bb0dae6d-91cc-417d-9493-08beebeec142	21	21	30.015	9.993	0
397	bb0dae6d-91cc-417d-9493-08beebeec142	22	22	29.972	6.33	0
398	bb0dae6d-91cc-417d-9493-08beebeec142	23	23	35.893	9.907	0
399	bb0dae6d-91cc-417d-9493-08beebeec142	3	3	18.004	1.985	0
400	bb0dae6d-91cc-417d-9493-08beebeec142	4	4	17.919	6.031	0
401	bb0dae6d-91cc-417d-9493-08beebeec142	5	5	10.081	6.117	0
402	bb0dae6d-91cc-417d-9493-08beebeec142	6	6	2.159	6.031	0
403	bb0dae6d-91cc-417d-9493-08beebeec142	7	7	1.946	9.907	0
404	bb0dae6d-91cc-417d-9493-08beebeec142	8	8	9.996	9.822	0
405	bb0dae6d-91cc-417d-9493-08beebeec142	9	9	18.004	9.993	0
406	703c7452-55bb-4e15-8304-f4e88ddbc2ba	1	1	14.574074074074074	7.833333333333333	0
407	9a861d33-52f1-4fa1-83d5-76da8fad400a	1	1	2	2	0
408	9a861d33-52f1-4fa1-83d5-76da8fad400a	10	10	18	6	0
409	9a861d33-52f1-4fa1-83d5-76da8fad400a	11	11	2	10	0
410	9a861d33-52f1-4fa1-83d5-76da8fad400a	12	12	6	10	0
411	9a861d33-52f1-4fa1-83d5-76da8fad400a	13	13	10	10	0
412	9a861d33-52f1-4fa1-83d5-76da8fad400a	14	14	14	10	0
413	9a861d33-52f1-4fa1-83d5-76da8fad400a	15	15	18	10	0
414	9a861d33-52f1-4fa1-83d5-76da8fad400a	16	16	10	6	0
415	9a861d33-52f1-4fa1-83d5-76da8fad400a	17	17	14	6	0
416	9a861d33-52f1-4fa1-83d5-76da8fad400a	18	18	10	10	0
417	9a861d33-52f1-4fa1-83d5-76da8fad400a	19	19	14	10	0
418	9a861d33-52f1-4fa1-83d5-76da8fad400a	2	2	6	2	0
419	9a861d33-52f1-4fa1-83d5-76da8fad400a	20	20	18	10	0
420	9a861d33-52f1-4fa1-83d5-76da8fad400a	3	3	10	2	0
421	9a861d33-52f1-4fa1-83d5-76da8fad400a	4	4	14	2	0
422	9a861d33-52f1-4fa1-83d5-76da8fad400a	5	5	18	2	0
423	9a861d33-52f1-4fa1-83d5-76da8fad400a	6	6	2	6	0
424	9a861d33-52f1-4fa1-83d5-76da8fad400a	7	7	6	6	0
425	9a861d33-52f1-4fa1-83d5-76da8fad400a	8	8	10	6	0
426	9a861d33-52f1-4fa1-83d5-76da8fad400a	9	9	14	6	0
427	cc51d003-010b-4a2d-8879-f312e80b2cfd	1	1	2	2	0
428	cc51d003-010b-4a2d-8879-f312e80b2cfd	10	10	18	6	0
429	cc51d003-010b-4a2d-8879-f312e80b2cfd	11	11	2	10	0
430	cc51d003-010b-4a2d-8879-f312e80b2cfd	12	12	6	10	0
431	cc51d003-010b-4a2d-8879-f312e80b2cfd	13	13	10	10	0
432	cc51d003-010b-4a2d-8879-f312e80b2cfd	14	14	14	10	0
433	cc51d003-010b-4a2d-8879-f312e80b2cfd	15	15	18	10	0
434	cc51d003-010b-4a2d-8879-f312e80b2cfd	16	16	10	6	0
435	cc51d003-010b-4a2d-8879-f312e80b2cfd	17	17	14	6	0
436	cc51d003-010b-4a2d-8879-f312e80b2cfd	18	18	10	10	0
437	cc51d003-010b-4a2d-8879-f312e80b2cfd	19	19	14	10	0
438	cc51d003-010b-4a2d-8879-f312e80b2cfd	2	2	6	2	0
439	cc51d003-010b-4a2d-8879-f312e80b2cfd	20	20	18	10	0
440	cc51d003-010b-4a2d-8879-f312e80b2cfd	3	3	10	2	0
441	cc51d003-010b-4a2d-8879-f312e80b2cfd	4	4	14	2	0
442	cc51d003-010b-4a2d-8879-f312e80b2cfd	5	5	18	2	0
443	cc51d003-010b-4a2d-8879-f312e80b2cfd	6	6	2	6	0
444	cc51d003-010b-4a2d-8879-f312e80b2cfd	7	7	6	6	0
445	cc51d003-010b-4a2d-8879-f312e80b2cfd	8	8	10	6	0
446	cc51d003-010b-4a2d-8879-f312e80b2cfd	9	9	14	6	0
447	cc16078b-cae9-40a3-ad3c-d74da64266f6	1	1	11.204	6.204	0
448	80	1	1	11.204	6.204	0
472	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	1	1	1.946	1.943	0
473	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	10	10	17.961	13.911	0
474	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	11	11	9.911	13.996	0
475	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	12	12	2.202	14.081	0
476	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	13	13	2.074	18.085	0
477	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	14	14	9.954	18.085	0
478	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	15	15	17.833	17.915	0
479	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	16	16	24.052	15.913	0
480	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	17	17	24.009	8.331	0
481	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	18	18	23.967	3.902	0
482	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	19	19	24.094	12.122	0
483	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	2	2	9.954	1.985	0
484	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	20	20	29.93	13.996	0
485	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	21	21	30.015	9.993	0
486	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	22	22	29.972	6.33	0
487	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	23	23	35.893	9.907	0
488	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	3	3	18.004	1.985	0
489	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	4	4	17.919	6.031	0
490	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	5	5	10.081	6.117	0
491	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	6	6	2.159	6.031	0
492	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	7	7	1.946	9.907	0
493	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	8	8	9.996	9.822	0
494	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	9	9	18.004	9.993	0
\.


--
-- Data for Name: agv_map_points; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agv_map_points (id, map_id, name_id, name, x, y, theta, type, zone, action, carrier, available, accuracy, speed) FROM stdin;
168	59	1		10.82258129119873	-2.29671311378479	1.663275718688965	0		\N	0	f	0	0.5
169	59	2		10.106666666666666	-0.06791666666667028	3.141592653589793	0		\N	0	f	0	0.5
170	59	3		7.2799999999999985	-1.1879166666666692	3.141592653589793	0		\N	0	f	0	0.5
180	99	11		15.315471649169922	0.8956514000892639	-1.6325205564498906	0		\N	0	f	0	0.5
181	99	14		14.191963005065917	0.8172676753997803	3.1140904426574707	0		\N	0	f	0	0.5
182	99	15		10.78326822916666	0.9951497395833201	2.5535900500422324	0		\N	0	f	0	0.5
183	99	16		18.250539779663086	0.75095534324646	3.1299555301666264	0		\N	0	f	0	0.5
184	99	18		6.067204258565174	2.434503161276921	-1.6124389058934852	0		\N	0	f	0	0.5
185	99	19		8.430276858981415	2.267171856617878	1.5063694873693434	0		\N	0	f	0	0.5
171	99	1		7.6451766967773445	-12.51909351348877	1.5178693532943728	0		\N	0	f	0	0.5
172	99	2		8.930188630123576	10.74792736740415	-0.08367857019276591	0		\N	0	f	0	0.5
173	99	3		19.9162094674884	10.3946839689834	-1.6351224745722082	0		\N	0	f	0	0.5
174	99	4		19.57169264444009	-0.741306406763161	-1.5638150097869097	0		\N	0	f	0	0.5
175	99	5		17.829244613647457	-7.077150090535475	-1.5707963267948963	0		\N	0	f	0	0.5
176	99	6		22.95619773864746	-12.285483423868811	0	0		\N	0	f	0	0.5
177	99	7		27.51348940531413	-13.424806340535476	0	0		\N	0	f	0	0.5
178	99	8		14.610569686889658	-10.163110898335777	-1.5707963267948963	0		\N	0	f	0	0.5
179	99	10		27.79301643371582	-11.047908782958984	-0.03628624230623239	0		\N	0	f	0	0.5
186	99	20	conv01	5.991900529882409	0.045537442879473033	1.513047927901089	0		{"locationType": "CONVEYOR", "defaultAction": "PICKUP"}	0	f	2	0.5
27	97	1		-18.667470932006836	10.810256958007812	0.16738557815551758	0		\N	0	f	0	0.5
28	97	2		-18.949315061188933	8.315894786082202	0.15613998689925176	0		\N	0	f	0	0.5
29	97	5		-16.24281627556118	8.846178793903523	-1.4146563398956444	0		\N	0	f	0	0.5
187	99	21	Kho Thành Phẩm	14.191511016650526	6.7011891784949915	-1.642103791580183	0		{"locationType": "DROPOFF", "defaultAction": "DROP"}	0	f	0	0.5
188	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	1		7.021	10.01	0	0		\N	0	f	0	0.5
189	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	10		3.999	15.787	0	0		\N	0	f	0	0.5
190	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	11		6.784	14.809	0	0		\N	0	f	0	0.5
191	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	12		3.199	13.328	0	0		\N	0	f	0	0.5
192	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	13		18.691	13.417	0	0		\N	0	f	0	0.5
193	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	14		21.12	10.455	0	0		\N	0	f	0	0.5
194	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	15		19.758	8.026	0	0		\N	0	f	0	0.5
195	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	16		16.618	13.269	0	0		\N	0	f	0	0.5
196	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	17		12.678	15.49	0	0		\N	0	f	0	0.5
197	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	18		11.612	3.879	0	0		\N	0	f	0	0.5
48	56	1		0.6292698979377747	-10.564980506896973	1.511621117591858	0		\N	0	f	0	0.5
49	56	2		0.7342950701713562	-8.304348945617676	1.5124090909957888	0		\N	0	f	0	0.5
50	56	3		-1.9831966161727905	-8.290040016174316	-3.1033356189727788	0		\N	0	f	0	0.5
51	56	4		0.6464591026306152	-6.204639434814453	1.5531911849975586	0		\N	0	f	0	0.5
52	56	5		4.985492706298828	-6.010046482086182	0.03343282267451282	0		\N	0	f	0	0.5
53	56	6		5.158753871917725	-1.3828330039978027	1.5473122596740723	0		\N	0	f	0	0.5
54	56	7		0.009482557885348797	-1.2471202611923218	-3.1391355991363525	0		\N	0	f	0	0.5
55	56	8		0.26875752210617065	6.701098918914795	1.5385612249374392	0		\N	0	f	0	0.5
56	56	9		0.3227335810661316	13.825260162353516	1.6239125728607176	0		\N	0	f	0	0.5
62	98	1		-11.469558715820312	16.204452514648438	2.969398975372315	0		\N	0	f	0	0.5
63	98	2		-16.930097579956055	17.904834747314453	2.8320653438568115	0		\N	0	f	0	0.5
64	98	3		-15.251384735107422	20.00648333231608	1.3909428270024204	0		\N	0	f	0	0.5
65	98	4		-14.501513671875001	15.051336924235025	-0.1607627406258351	0		\N	0	f	0	0.5
66	98	5		-11.468180338541668	18.08467025756836	-0.030293759918778758	0		\N	0	f	0	0.5
97	87	1		-14.587265968322754	-8.011516571044922	-1.5949119329452515	0		\N	0	f	0	0.5
98	87	2		-14.66279296875	-5.634148120880127	1.5952872037887573	0		\N	0	f	0	0.5
99	87	3		-14.570400047302247	-3.3296561241149902	1.5360957384109497	0		\N	0	f	0	0.5
100	87	4		-14.478529357910157	0.19267681241035461	1.5287697315216064	0		\N	0	f	0	0.5
101	87	5		-14.385263442993164	3.389639377593994	1.5463557243347168	0		\N	0	f	0	0.5
102	87	6		-14.331920623779297	6.4980244636535645	1.5517145395278928	0		\N	0	f	0	0.5
103	87	7		-14.249767303466797	8.901872634887695	1.510737657546997	0		\N	0	f	0	0.5
104	87	8		-14.274264335632324	11.660944938659668	1.5565301179885864	0		\N	0	f	0	0.5
105	87	9		-7.6139068603515625	11.903380393981934	0.06421291828155516	0		\N	0	f	0	0.5
198	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	19		16.262	3.731	0	0		\N	0	f	0	0.5
199	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	2		11.167	13.061	0	0		\N	0	f	0	0.5
200	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	20		21.861	4.205	0	4		\N	0	f	0	0.5
201	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	21		4.177	4.708	0	0		\N	0	f	0	0.5
202	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	22		3.051	8.144	0	0		\N	0	f	0	0.5
203	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	23		12.797	7.493	0	0		\N	0	f	0	0.5
204	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	24		10.111	7.978	0	4		\N	0	f	0	0.5
205	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	25		20.094	19.948	0	0		\N	0	f	0	0.5
206	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	26		24.678	13.225	0	0		\N	0	f	0	0.5
207	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	27		25.086	7.112	0	0		\N	0	f	0	0.5
208	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	28		39.972	17.083	0	4		\N	0	f	0	0.5
209	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	3		11.049	17.149	0	0		\N	0	f	0	0.5
210	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	4		15.077	17.653	0	0		\N	0	f	0	0.5
211	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	5		18.128	15.224	0	0		\N	0	f	0	0.5
212	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	6		18.04	19.933	0	0		\N	0	f	0	0.5
213	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	7		10.486	19.637	0	0		\N	0	f	0	0.5
214	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	8		6.961	18.452	0	0		\N	0	f	0	0.5
215	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	9		5.184	21.029	0	4		\N	0	f	0	0.5
216	4001ae10-9a25-4f79-9941-6bfc467df987	1		2	2	0	1		\N	0	f	0	0.5
217	4001ae10-9a25-4f79-9941-6bfc467df987	10		18	6	0	1		\N	0	f	0	0.5
218	4001ae10-9a25-4f79-9941-6bfc467df987	11		2	10	0	3		\N	0	f	0	0.5
219	4001ae10-9a25-4f79-9941-6bfc467df987	12		6	10	0	0		\N	0	f	0	0.5
220	4001ae10-9a25-4f79-9941-6bfc467df987	13		10	10	0	1		\N	0	f	0	0.5
221	4001ae10-9a25-4f79-9941-6bfc467df987	14		14	10	0	0		\N	0	f	0	0.5
222	4001ae10-9a25-4f79-9941-6bfc467df987	15		18	10	0	3		\N	0	f	0	0.5
223	4001ae10-9a25-4f79-9941-6bfc467df987	16		10	6	0	4		\N	0	f	0	0.5
224	4001ae10-9a25-4f79-9941-6bfc467df987	17		14	6	0	0		\N	0	f	0	0.5
225	4001ae10-9a25-4f79-9941-6bfc467df987	18		10	10	0	1		\N	0	f	0	0.5
226	4001ae10-9a25-4f79-9941-6bfc467df987	19		14	10	0	0		\N	0	f	0	0.5
227	4001ae10-9a25-4f79-9941-6bfc467df987	2		6	2	0	0		\N	0	f	0	0.5
228	4001ae10-9a25-4f79-9941-6bfc467df987	20		18	10	0	3		\N	0	f	0	0.5
229	4001ae10-9a25-4f79-9941-6bfc467df987	3		10	2	0	1		\N	0	f	0	0.5
230	4001ae10-9a25-4f79-9941-6bfc467df987	4		14	2	0	0		\N	0	f	0	0.5
231	4001ae10-9a25-4f79-9941-6bfc467df987	5		18	2	0	1		\N	0	f	0	0.5
232	4001ae10-9a25-4f79-9941-6bfc467df987	6		2	6	0	0		\N	0	f	0	0.5
233	4001ae10-9a25-4f79-9941-6bfc467df987	7		6	6	0	0		\N	0	f	0	0.5
234	4001ae10-9a25-4f79-9941-6bfc467df987	8		10	6	0	4		\N	0	f	0	0.5
235	4001ae10-9a25-4f79-9941-6bfc467df987	9		14	6	0	0		\N	0	f	0	0.5
236	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	1		2	2	0	1		\N	0	f	0	0.5
237	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	10		18	6	0	1		\N	0	f	0	0.5
238	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	11		2	10	0	3		\N	0	f	0	0.5
239	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	12		6	10	0	0		\N	0	f	0	0.5
240	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	13		10	10	0	1		\N	0	f	0	0.5
241	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	14		14	10	0	0		\N	0	f	0	0.5
242	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	15		18	10	0	3		\N	0	f	0	0.5
243	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	16		10	6	0	4		\N	0	f	0	0.5
244	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	17		14	6	0	0		\N	0	f	0	0.5
245	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	18		10	10	0	1		\N	0	f	0	0.5
246	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	19		14	10	0	0		\N	0	f	0	0.5
247	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	2		6	2	0	0		\N	0	f	0	0.5
248	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	20		18	10	0	3		\N	0	f	0	0.5
249	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	3		10	2	0	1		\N	0	f	0	0.5
250	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	4		14	2	0	0		\N	0	f	0	0.5
251	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	5		18	2	0	1		\N	0	f	0	0.5
252	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	6		2	6	0	0		\N	0	f	0	0.5
253	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	7		6	6	0	0		\N	0	f	0	0.5
254	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	8		10	6	0	4		\N	0	f	0	0.5
255	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	9		14	6	0	0		\N	0	f	0	0.5
256	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	1		2	2	0	1		\N	0	f	0	0.5
257	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	10		18	6	0	1		\N	0	f	0	0.5
258	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	11		2	10	0	3		\N	0	f	0	0.5
259	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	12		6	10	0	0		\N	0	f	0	0.5
260	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	13		10	10	0	1		\N	0	f	0	0.5
261	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	14		14	10	0	0		\N	0	f	0	0.5
262	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	15		18	10	0	3		\N	0	f	0	0.5
263	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	16		10	6	0	4		\N	0	f	0	0.5
264	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	17		14	6	0	0		\N	0	f	0	0.5
265	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	18		10	10	0	1		\N	0	f	0	0.5
266	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	19		14	10	0	0		\N	0	f	0	0.5
267	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	2		6	2	0	0		\N	0	f	0	0.5
268	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	20		18	10	0	3		\N	0	f	0	0.5
269	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	3		10	2	0	1		\N	0	f	0	0.5
270	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	4		14	2	0	0		\N	0	f	0	0.5
271	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	5		18	2	0	1		\N	0	f	0	0.5
272	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	6		2	6	0	0		\N	0	f	0	0.5
273	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	7		6	6	0	0		\N	0	f	0	0.5
274	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	8		10	6	0	4		\N	0	f	0	0.5
275	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	9		14	6	0	0		\N	0	f	0	0.5
276	4656f23b-ed40-43d1-a314-94bbdedf5d29	1		2	2	0	1		\N	0	f	0	0.5
277	4656f23b-ed40-43d1-a314-94bbdedf5d29	10		18	6	0	1		\N	0	f	0	0.5
278	4656f23b-ed40-43d1-a314-94bbdedf5d29	11		2	10	0	3		\N	0	f	0	0.5
279	4656f23b-ed40-43d1-a314-94bbdedf5d29	12		6	10	0	0		\N	0	f	0	0.5
280	4656f23b-ed40-43d1-a314-94bbdedf5d29	13		10	10	0	1		\N	0	f	0	0.5
281	4656f23b-ed40-43d1-a314-94bbdedf5d29	14		14	10	0	0		\N	0	f	0	0.5
282	4656f23b-ed40-43d1-a314-94bbdedf5d29	15		18	10	0	3		\N	0	f	0	0.5
283	4656f23b-ed40-43d1-a314-94bbdedf5d29	16		10	6	0	4		\N	0	f	0	0.5
284	4656f23b-ed40-43d1-a314-94bbdedf5d29	17		14	6	0	0		\N	0	f	0	0.5
285	4656f23b-ed40-43d1-a314-94bbdedf5d29	18		10	10	0	1		\N	0	f	0	0.5
286	4656f23b-ed40-43d1-a314-94bbdedf5d29	19		14	10	0	0		\N	0	f	0	0.5
287	4656f23b-ed40-43d1-a314-94bbdedf5d29	2		6	2	0	0		\N	0	f	0	0.5
288	4656f23b-ed40-43d1-a314-94bbdedf5d29	20		18	10	0	3		\N	0	f	0	0.5
289	4656f23b-ed40-43d1-a314-94bbdedf5d29	3		10	2	0	1		\N	0	f	0	0.5
290	4656f23b-ed40-43d1-a314-94bbdedf5d29	4		14	2	0	0		\N	0	f	0	0.5
291	4656f23b-ed40-43d1-a314-94bbdedf5d29	5		18	2	0	1		\N	0	f	0	0.5
292	4656f23b-ed40-43d1-a314-94bbdedf5d29	6		2	6	0	0		\N	0	f	0	0.5
293	4656f23b-ed40-43d1-a314-94bbdedf5d29	7		6	6	0	0		\N	0	f	0	0.5
294	4656f23b-ed40-43d1-a314-94bbdedf5d29	8		10	6	0	4		\N	0	f	0	0.5
295	4656f23b-ed40-43d1-a314-94bbdedf5d29	9		14	6	0	0		\N	0	f	0	0.5
296	ceed0bd3-7f76-46e4-b188-61010dcd100a	1		2	2	0	1		\N	0	f	0	0.5
297	ceed0bd3-7f76-46e4-b188-61010dcd100a	10		18	6	0	1		\N	0	f	0	0.5
298	ceed0bd3-7f76-46e4-b188-61010dcd100a	11		2	10	0	3		\N	0	f	0	0.5
299	ceed0bd3-7f76-46e4-b188-61010dcd100a	12		6	10	0	0		\N	0	f	0	0.5
300	ceed0bd3-7f76-46e4-b188-61010dcd100a	13		10	10	0	1		\N	0	f	0	0.5
301	ceed0bd3-7f76-46e4-b188-61010dcd100a	14		14	10	0	0		\N	0	f	0	0.5
302	ceed0bd3-7f76-46e4-b188-61010dcd100a	15		18	10	0	3		\N	0	f	0	0.5
303	ceed0bd3-7f76-46e4-b188-61010dcd100a	16		10	6	0	4		\N	0	f	0	0.5
304	ceed0bd3-7f76-46e4-b188-61010dcd100a	17		14	6	0	0		\N	0	f	0	0.5
305	ceed0bd3-7f76-46e4-b188-61010dcd100a	18		10	10	0	1		\N	0	f	0	0.5
306	ceed0bd3-7f76-46e4-b188-61010dcd100a	19		14	10	0	0		\N	0	f	0	0.5
307	ceed0bd3-7f76-46e4-b188-61010dcd100a	2		6	2	0	0		\N	0	f	0	0.5
308	ceed0bd3-7f76-46e4-b188-61010dcd100a	20		18	10	0	3		\N	0	f	0	0.5
309	ceed0bd3-7f76-46e4-b188-61010dcd100a	3		10	2	0	1		\N	0	f	0	0.5
310	ceed0bd3-7f76-46e4-b188-61010dcd100a	4		14	2	0	0		\N	0	f	0	0.5
311	ceed0bd3-7f76-46e4-b188-61010dcd100a	5		18	2	0	1		\N	0	f	0	0.5
312	ceed0bd3-7f76-46e4-b188-61010dcd100a	6		2	6	0	0		\N	0	f	0	0.5
313	ceed0bd3-7f76-46e4-b188-61010dcd100a	7		6	6	0	0		\N	0	f	0	0.5
314	ceed0bd3-7f76-46e4-b188-61010dcd100a	8		10	6	0	4		\N	0	f	0	0.5
315	ceed0bd3-7f76-46e4-b188-61010dcd100a	9		14	6	0	0		\N	0	f	0	0.5
316	98162503-c3c3-452f-a896-e85ded516cb9	1		2	2	0	1		\N	0	f	0	0.5
317	98162503-c3c3-452f-a896-e85ded516cb9	10		18	6	0	1		\N	0	f	0	0.5
318	98162503-c3c3-452f-a896-e85ded516cb9	11		2	10	0	3		\N	0	f	0	0.5
319	98162503-c3c3-452f-a896-e85ded516cb9	12		6	10	0	0		\N	0	f	0	0.5
320	98162503-c3c3-452f-a896-e85ded516cb9	13		10	10	0	1		\N	0	f	0	0.5
321	98162503-c3c3-452f-a896-e85ded516cb9	14		14	10	0	0		\N	0	f	0	0.5
322	98162503-c3c3-452f-a896-e85ded516cb9	15		18	10	0	3		\N	0	f	0	0.5
323	98162503-c3c3-452f-a896-e85ded516cb9	16		10	6	0	4		\N	0	f	0	0.5
324	98162503-c3c3-452f-a896-e85ded516cb9	17		14	6	0	0		\N	0	f	0	0.5
325	98162503-c3c3-452f-a896-e85ded516cb9	18		10	10	0	1		\N	0	f	0	0.5
326	98162503-c3c3-452f-a896-e85ded516cb9	19		14	10	0	0		\N	0	f	0	0.5
327	98162503-c3c3-452f-a896-e85ded516cb9	2		6	2	0	0		\N	0	f	0	0.5
328	98162503-c3c3-452f-a896-e85ded516cb9	20		18	10	0	3		\N	0	f	0	0.5
329	98162503-c3c3-452f-a896-e85ded516cb9	3		10	2	0	1		\N	0	f	0	0.5
330	98162503-c3c3-452f-a896-e85ded516cb9	4		14	2	0	0		\N	0	f	0	0.5
331	98162503-c3c3-452f-a896-e85ded516cb9	5		18	2	0	1		\N	0	f	0	0.5
332	98162503-c3c3-452f-a896-e85ded516cb9	6		2	6	0	0		\N	0	f	0	0.5
333	98162503-c3c3-452f-a896-e85ded516cb9	7		6	6	0	0		\N	0	f	0	0.5
334	98162503-c3c3-452f-a896-e85ded516cb9	8		10	6	0	4		\N	0	f	0	0.5
335	98162503-c3c3-452f-a896-e85ded516cb9	9		14	6	0	0		\N	0	f	0	0.5
336	b6fcdc48-990f-4dfd-a50e-2eabca664196	1		2	2	0	1		\N	0	f	0	0.5
337	b6fcdc48-990f-4dfd-a50e-2eabca664196	10		18	6	0	1		\N	0	f	0	0.5
338	b6fcdc48-990f-4dfd-a50e-2eabca664196	11		2	10	0	3		\N	0	f	0	0.5
339	b6fcdc48-990f-4dfd-a50e-2eabca664196	12		6	10	0	0		\N	0	f	0	0.5
340	b6fcdc48-990f-4dfd-a50e-2eabca664196	13		10	10	0	1		\N	0	f	0	0.5
341	b6fcdc48-990f-4dfd-a50e-2eabca664196	14		14	10	0	0		\N	0	f	0	0.5
342	b6fcdc48-990f-4dfd-a50e-2eabca664196	15		18	10	0	3		\N	0	f	0	0.5
343	b6fcdc48-990f-4dfd-a50e-2eabca664196	16		10	6	0	4		\N	0	f	0	0.5
344	b6fcdc48-990f-4dfd-a50e-2eabca664196	17		14	6	0	0		\N	0	f	0	0.5
345	b6fcdc48-990f-4dfd-a50e-2eabca664196	18		10	10	0	1		\N	0	f	0	0.5
346	b6fcdc48-990f-4dfd-a50e-2eabca664196	19		14	10	0	0		\N	0	f	0	0.5
347	b6fcdc48-990f-4dfd-a50e-2eabca664196	2		6	2	0	0		\N	0	f	0	0.5
348	b6fcdc48-990f-4dfd-a50e-2eabca664196	20		18	10	0	3		\N	0	f	0	0.5
349	b6fcdc48-990f-4dfd-a50e-2eabca664196	3		10	2	0	1		\N	0	f	0	0.5
350	b6fcdc48-990f-4dfd-a50e-2eabca664196	4		14	2	0	0		\N	0	f	0	0.5
351	b6fcdc48-990f-4dfd-a50e-2eabca664196	5		18	2	0	1		\N	0	f	0	0.5
352	b6fcdc48-990f-4dfd-a50e-2eabca664196	6		2	6	0	0		\N	0	f	0	0.5
353	b6fcdc48-990f-4dfd-a50e-2eabca664196	7		6	6	0	0		\N	0	f	0	0.5
354	b6fcdc48-990f-4dfd-a50e-2eabca664196	8		10	6	0	4		\N	0	f	0	0.5
355	b6fcdc48-990f-4dfd-a50e-2eabca664196	9		14	6	0	0		\N	0	f	0	0.5
356	61d76858-93a2-413d-9840-ea136908c9ab	1		2	2	0	1		\N	0	f	0	0.5
357	61d76858-93a2-413d-9840-ea136908c9ab	10		18	6	0	1		\N	0	f	0	0.5
358	61d76858-93a2-413d-9840-ea136908c9ab	11		2	10	0	3		\N	0	f	0	0.5
359	61d76858-93a2-413d-9840-ea136908c9ab	12		6	10	0	0		\N	0	f	0	0.5
360	61d76858-93a2-413d-9840-ea136908c9ab	13		10	10	0	1		\N	0	f	0	0.5
361	61d76858-93a2-413d-9840-ea136908c9ab	14		14	10	0	0		\N	0	f	0	0.5
362	61d76858-93a2-413d-9840-ea136908c9ab	15		18	10	0	3		\N	0	f	0	0.5
363	61d76858-93a2-413d-9840-ea136908c9ab	16		10	6	0	4		\N	0	f	0	0.5
364	61d76858-93a2-413d-9840-ea136908c9ab	17		14	6	0	0		\N	0	f	0	0.5
365	61d76858-93a2-413d-9840-ea136908c9ab	18		10	10	0	1		\N	0	f	0	0.5
366	61d76858-93a2-413d-9840-ea136908c9ab	19		14	10	0	0		\N	0	f	0	0.5
367	61d76858-93a2-413d-9840-ea136908c9ab	2		6	2	0	0		\N	0	f	0	0.5
368	61d76858-93a2-413d-9840-ea136908c9ab	20		18	10	0	3		\N	0	f	0	0.5
369	61d76858-93a2-413d-9840-ea136908c9ab	3		10	2	0	1		\N	0	f	0	0.5
370	61d76858-93a2-413d-9840-ea136908c9ab	4		14	2	0	0		\N	0	f	0	0.5
371	61d76858-93a2-413d-9840-ea136908c9ab	5		18	2	0	1		\N	0	f	0	0.5
372	61d76858-93a2-413d-9840-ea136908c9ab	6		2	6	0	0		\N	0	f	0	0.5
373	61d76858-93a2-413d-9840-ea136908c9ab	7		6	6	0	0		\N	0	f	0	0.5
374	61d76858-93a2-413d-9840-ea136908c9ab	8		10	6	0	4		\N	0	f	0	0.5
375	61d76858-93a2-413d-9840-ea136908c9ab	9		14	6	0	0		\N	0	f	0	0.5
376	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	1		2	2	0	1		\N	0	f	0	0.5
377	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	10		18	6	0	1		\N	0	f	0	0.5
378	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	11		2	10	0	3		\N	0	f	0	0.5
379	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	12		6	10	0	0		\N	0	f	0	0.5
380	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	13		10	10	0	1		\N	0	f	0	0.5
381	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	14		14	10	0	0		\N	0	f	0	0.5
382	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	15		18	10	0	3		\N	0	f	0	0.5
383	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	16		10	6	0	4		\N	0	f	0	0.5
384	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	17		14	6	0	0		\N	0	f	0	0.5
385	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	18		10	10	0	1		\N	0	f	0	0.5
386	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	19		14	10	0	0		\N	0	f	0	0.5
387	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	2		6	2	0	0		\N	0	f	0	0.5
388	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	20		18	10	0	3		\N	0	f	0	0.5
389	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	3		10	2	0	1		\N	0	f	0	0.5
390	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	4		14	2	0	0		\N	0	f	0	0.5
391	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	5		18	2	0	1		\N	0	f	0	0.5
392	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	6		2	6	0	0		\N	0	f	0	0.5
393	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	7		6	6	0	0		\N	0	f	0	0.5
394	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	8		10	6	0	4		\N	0	f	0	0.5
395	f54ea27c-6e7d-4a6e-b45f-28e814b2e378	9		14	6	0	0		\N	0	f	0	0.5
396	88173d83-9aa6-4df1-aaa8-c06b63569fc5	1		2	2	0	1		\N	0	f	0	0.5
397	88173d83-9aa6-4df1-aaa8-c06b63569fc5	10		18	6	0	1		\N	0	f	0	0.5
398	88173d83-9aa6-4df1-aaa8-c06b63569fc5	11		2	10	0	3		\N	0	f	0	0.5
399	88173d83-9aa6-4df1-aaa8-c06b63569fc5	12		6	10	0	0		\N	0	f	0	0.5
400	88173d83-9aa6-4df1-aaa8-c06b63569fc5	13		10	10	0	1		\N	0	f	0	0.5
401	88173d83-9aa6-4df1-aaa8-c06b63569fc5	14		14	10	0	0		\N	0	f	0	0.5
402	88173d83-9aa6-4df1-aaa8-c06b63569fc5	15		18	10	0	3		\N	0	f	0	0.5
403	88173d83-9aa6-4df1-aaa8-c06b63569fc5	16		10	6	0	4		\N	0	f	0	0.5
404	88173d83-9aa6-4df1-aaa8-c06b63569fc5	17		14	6	0	0		\N	0	f	0	0.5
405	88173d83-9aa6-4df1-aaa8-c06b63569fc5	18		10	10	0	1		\N	0	f	0	0.5
406	88173d83-9aa6-4df1-aaa8-c06b63569fc5	19		14	10	0	0		\N	0	f	0	0.5
407	88173d83-9aa6-4df1-aaa8-c06b63569fc5	2		6	2	0	0		\N	0	f	0	0.5
408	88173d83-9aa6-4df1-aaa8-c06b63569fc5	20		18	10	0	3		\N	0	f	0	0.5
409	88173d83-9aa6-4df1-aaa8-c06b63569fc5	3		10	2	0	1		\N	0	f	0	0.5
410	88173d83-9aa6-4df1-aaa8-c06b63569fc5	4		14	2	0	0		\N	0	f	0	0.5
411	88173d83-9aa6-4df1-aaa8-c06b63569fc5	5		18	2	0	1		\N	0	f	0	0.5
412	88173d83-9aa6-4df1-aaa8-c06b63569fc5	6		2	6	0	0		\N	0	f	0	0.5
413	88173d83-9aa6-4df1-aaa8-c06b63569fc5	7		6	6	0	0		\N	0	f	0	0.5
414	88173d83-9aa6-4df1-aaa8-c06b63569fc5	8		10	6	0	4		\N	0	f	0	0.5
415	88173d83-9aa6-4df1-aaa8-c06b63569fc5	9		14	6	0	0		\N	0	f	0	0.5
416	b7badbae-9aaf-4f4a-9ed0-87096255212c	1		2	2	0	1		\N	0	f	0	0.5
417	b7badbae-9aaf-4f4a-9ed0-87096255212c	10		18	6	0	1		\N	0	f	0	0.5
418	b7badbae-9aaf-4f4a-9ed0-87096255212c	11		2	10	0	3		\N	0	f	0	0.5
419	b7badbae-9aaf-4f4a-9ed0-87096255212c	12		6	10	0	0		\N	0	f	0	0.5
420	b7badbae-9aaf-4f4a-9ed0-87096255212c	13		10	10	0	1		\N	0	f	0	0.5
421	b7badbae-9aaf-4f4a-9ed0-87096255212c	14		14	10	0	0		\N	0	f	0	0.5
422	b7badbae-9aaf-4f4a-9ed0-87096255212c	15		18	10	0	3		\N	0	f	0	0.5
423	b7badbae-9aaf-4f4a-9ed0-87096255212c	16		10	6	0	4		\N	0	f	0	0.5
424	b7badbae-9aaf-4f4a-9ed0-87096255212c	17		14	6	0	0		\N	0	f	0	0.5
425	b7badbae-9aaf-4f4a-9ed0-87096255212c	18		10	10	0	1		\N	0	f	0	0.5
426	b7badbae-9aaf-4f4a-9ed0-87096255212c	19		14	10	0	0		\N	0	f	0	0.5
427	b7badbae-9aaf-4f4a-9ed0-87096255212c	2		6	2	0	0		\N	0	f	0	0.5
428	b7badbae-9aaf-4f4a-9ed0-87096255212c	20		18	10	0	3		\N	0	f	0	0.5
429	b7badbae-9aaf-4f4a-9ed0-87096255212c	3		10	2	0	1		\N	0	f	0	0.5
430	b7badbae-9aaf-4f4a-9ed0-87096255212c	4		14	2	0	0		\N	0	f	0	0.5
431	b7badbae-9aaf-4f4a-9ed0-87096255212c	5		18	2	0	1		\N	0	f	0	0.5
432	b7badbae-9aaf-4f4a-9ed0-87096255212c	6		2	6	0	0		\N	0	f	0	0.5
433	b7badbae-9aaf-4f4a-9ed0-87096255212c	7		6	6	0	0		\N	0	f	0	0.5
434	b7badbae-9aaf-4f4a-9ed0-87096255212c	8		10	6	0	4		\N	0	f	0	0.5
435	b7badbae-9aaf-4f4a-9ed0-87096255212c	9		14	6	0	0		\N	0	f	0	0.5
436	3772fe6a-6a43-4c30-a40e-125ddc5598c4	1		2	2	0	1		\N	0	f	0	0.5
437	3772fe6a-6a43-4c30-a40e-125ddc5598c4	10		18	6	0	1		\N	0	f	0	0.5
438	3772fe6a-6a43-4c30-a40e-125ddc5598c4	11		2	10	0	3		\N	0	f	0	0.5
439	3772fe6a-6a43-4c30-a40e-125ddc5598c4	12		6	10	0	0		\N	0	f	0	0.5
440	3772fe6a-6a43-4c30-a40e-125ddc5598c4	13		10	10	0	1		\N	0	f	0	0.5
441	3772fe6a-6a43-4c30-a40e-125ddc5598c4	14		14	10	0	0		\N	0	f	0	0.5
442	3772fe6a-6a43-4c30-a40e-125ddc5598c4	15		18	10	0	3		\N	0	f	0	0.5
443	3772fe6a-6a43-4c30-a40e-125ddc5598c4	16		10	6	0	4		\N	0	f	0	0.5
444	3772fe6a-6a43-4c30-a40e-125ddc5598c4	17		14	6	0	0		\N	0	f	0	0.5
445	3772fe6a-6a43-4c30-a40e-125ddc5598c4	18		10	10	0	1		\N	0	f	0	0.5
446	3772fe6a-6a43-4c30-a40e-125ddc5598c4	19		14	10	0	0		\N	0	f	0	0.5
447	3772fe6a-6a43-4c30-a40e-125ddc5598c4	2		6	2	0	0		\N	0	f	0	0.5
448	3772fe6a-6a43-4c30-a40e-125ddc5598c4	20		18	10	0	3		\N	0	f	0	0.5
449	3772fe6a-6a43-4c30-a40e-125ddc5598c4	3		10	2	0	1		\N	0	f	0	0.5
450	3772fe6a-6a43-4c30-a40e-125ddc5598c4	4		14	2	0	0		\N	0	f	0	0.5
451	3772fe6a-6a43-4c30-a40e-125ddc5598c4	5		18	2	0	1		\N	0	f	0	0.5
452	3772fe6a-6a43-4c30-a40e-125ddc5598c4	6		2	6	0	0		\N	0	f	0	0.5
453	3772fe6a-6a43-4c30-a40e-125ddc5598c4	7		6	6	0	0		\N	0	f	0	0.5
454	3772fe6a-6a43-4c30-a40e-125ddc5598c4	8		10	6	0	4		\N	0	f	0	0.5
455	3772fe6a-6a43-4c30-a40e-125ddc5598c4	9		14	6	0	0		\N	0	f	0	0.5
456	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	1		2	2	0	1		\N	0	f	0	0.5
457	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	10		18	6	0	1		\N	0	f	0	0.5
458	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	11		2	10	0	3		\N	0	f	0	0.5
459	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	12		6	10	0	0		\N	0	f	0	0.5
460	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	13		10	10	0	1		\N	0	f	0	0.5
461	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	14		14	10	0	0		\N	0	f	0	0.5
462	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	15		18	10	0	3		\N	0	f	0	0.5
463	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	16		10	6	0	4		\N	0	f	0	0.5
464	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	17		14	6	0	0		\N	0	f	0	0.5
465	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	18		10	10	0	1		\N	0	f	0	0.5
466	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	19		14	10	0	0		\N	0	f	0	0.5
467	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	2		6	2	0	0		\N	0	f	0	0.5
468	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	20		18	10	0	3		\N	0	f	0	0.5
469	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	3		10	2	0	1		\N	0	f	0	0.5
470	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	4		14	2	0	0		\N	0	f	0	0.5
471	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	5		18	2	0	1		\N	0	f	0	0.5
472	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	6		2	6	0	0		\N	0	f	0	0.5
473	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	7		6	6	0	0		\N	0	f	0	0.5
474	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	8		10	6	0	4		\N	0	f	0	0.5
475	37b3a676-aa46-4650-aa23-9fa08b2c9e4f	9		14	6	0	0		\N	0	f	0	0.5
476	523fb5c2-e610-4f58-b471-646e295b8f15	1		2.037037037037037	11.981481481481481	0	0		\N	0	f	0	0.5
477	523fb5c2-e610-4f58-b471-646e295b8f15	10		4.925925925925926	4.018518518518518	0	0		\N	0	f	0	0.5
478	523fb5c2-e610-4f58-b471-646e295b8f15	11		8	12	0	0		\N	0	f	0	0.5
479	523fb5c2-e610-4f58-b471-646e295b8f15	12		7.981481481481482	10.055555555555555	0	0		\N	0	f	0	0.5
480	523fb5c2-e610-4f58-b471-646e295b8f15	13		7.907407407407407	8.055555555555555	0	0		\N	0	f	0	0.5
481	523fb5c2-e610-4f58-b471-646e295b8f15	14		7.981481481481482	6.037037037037037	0	0		\N	0	f	0	0.5
482	523fb5c2-e610-4f58-b471-646e295b8f15	15		8	4	0	0		\N	0	f	0	0.5
483	523fb5c2-e610-4f58-b471-646e295b8f15	16		10.981481481481481	4	0	0		\N	0	f	0	0.5
484	523fb5c2-e610-4f58-b471-646e295b8f15	17		11.037037037037036	6	0	0		\N	0	f	0	0.5
485	523fb5c2-e610-4f58-b471-646e295b8f15	18		11.037037037037036	8	0	0		\N	0	f	0	0.5
486	523fb5c2-e610-4f58-b471-646e295b8f15	19		10.944444444444445	9.88888888888889	0	0		\N	0	f	0	0.5
487	523fb5c2-e610-4f58-b471-646e295b8f15	2		1.9814814814814814	9.981481481481481	0	0		\N	0	f	0	0.5
488	523fb5c2-e610-4f58-b471-646e295b8f15	20		10.925925925925926	11.962962962962964	0	0		\N	0	f	0	0.5
489	523fb5c2-e610-4f58-b471-646e295b8f15	21		14.962962962962964	12	0	0		\N	0	f	0	0.5
490	523fb5c2-e610-4f58-b471-646e295b8f15	22		13.962962962962964	10.074074074074074	0	0		\N	0	f	0	0.5
491	523fb5c2-e610-4f58-b471-646e295b8f15	23		13.851851851851851	7.2407407407407405	0	0		\N	0	f	0	0.5
492	523fb5c2-e610-4f58-b471-646e295b8f15	24		14.648148148148149	5.111111111111111	0	0		\N	0	f	0	0.5
493	523fb5c2-e610-4f58-b471-646e295b8f15	25		17.09259259259259	3.9074074074074066	0	0		\N	0	f	0	0.5
494	523fb5c2-e610-4f58-b471-646e295b8f15	26		17.11111111111111	7.462962962962963	0	0		\N	0	f	0	0.5
495	523fb5c2-e610-4f58-b471-646e295b8f15	27		16.574074074074073	10.055555555555555	0	0		\N	0	f	0	0.5
496	523fb5c2-e610-4f58-b471-646e295b8f15	3		1.9814814814814814	8	0	0		\N	0	f	0	0.5
497	523fb5c2-e610-4f58-b471-646e295b8f15	4		2	5.981481481481482	0	0		\N	0	f	0	0.5
498	523fb5c2-e610-4f58-b471-646e295b8f15	5		1.962962962962963	3.9259259259259256	0	0		\N	0	f	0	0.5
499	523fb5c2-e610-4f58-b471-646e295b8f15	6		5	11.981481481481481	0	0		\N	0	f	0	0.5
500	523fb5c2-e610-4f58-b471-646e295b8f15	7		4.981481481481482	10	0	0		\N	0	f	0	0.5
501	523fb5c2-e610-4f58-b471-646e295b8f15	8		4.981481481481482	8	0	0		\N	0	f	0	0.5
502	523fb5c2-e610-4f58-b471-646e295b8f15	9		4.981481481481482	6.037037037037037	0	0		\N	0	f	0	0.5
503	93e3ba66-0f9a-4267-95a1-71872f181779	1		1.9462962962962969	1.942592592592593	0	0		\N	0	f	0	0.5
504	93e3ba66-0f9a-4267-95a1-71872f181779	10		17.961111111111112	13.911111111111111	0	0		\N	0	f	0	0.5
505	93e3ba66-0f9a-4267-95a1-71872f181779	11		9.911111111111111	13.996296296296297	0	0		\N	0	f	0	0.5
506	93e3ba66-0f9a-4267-95a1-71872f181779	12		2.2018518518518526	14.081481481481482	0	0		\N	0	f	0	0.5
507	93e3ba66-0f9a-4267-95a1-71872f181779	13		2.074074074074075	18.085185185185185	0	0		\N	0	f	0	0.5
508	93e3ba66-0f9a-4267-95a1-71872f181779	14		9.953703703703704	18.085185185185185	0	0		\N	0	f	0	0.5
509	93e3ba66-0f9a-4267-95a1-71872f181779	15		17.833333333333332	17.914814814814815	0	0		\N	0	f	0	0.5
510	93e3ba66-0f9a-4267-95a1-71872f181779	16		24.05185185185185	15.912962962962963	0	0		\N	0	f	0	0.5
511	93e3ba66-0f9a-4267-95a1-71872f181779	17		24.009259259259256	8.331481481481482	0	0		\N	0	f	0	0.5
512	93e3ba66-0f9a-4267-95a1-71872f181779	18		23.966666666666665	3.901851851851852	0	0		\N	0	f	0	0.5
513	93e3ba66-0f9a-4267-95a1-71872f181779	19		24.09444444444444	12.122222222222224	0	0		\N	0	f	0	0.5
514	93e3ba66-0f9a-4267-95a1-71872f181779	2		9.953703703703704	1.9851851851851876	0	0		\N	0	f	0	0.5
515	93e3ba66-0f9a-4267-95a1-71872f181779	20		29.929629629629627	13.996296296296297	0	0		\N	0	f	0	0.5
516	93e3ba66-0f9a-4267-95a1-71872f181779	21		30.014814814814812	9.992592592592594	0	0		\N	0	f	0	0.5
517	93e3ba66-0f9a-4267-95a1-71872f181779	22		29.972222222222218	6.329629629629631	0	0		\N	0	f	0	0.5
518	93e3ba66-0f9a-4267-95a1-71872f181779	23		35.89259259259259	9.907407407407408	0	0		\N	0	f	0	0.5
519	93e3ba66-0f9a-4267-95a1-71872f181779	3		18.003703703703703	1.9851851851851876	0	0		\N	0	f	0	0.5
520	93e3ba66-0f9a-4267-95a1-71872f181779	4		17.918518518518518	6.031481481481482	0	0		\N	0	f	0	0.5
521	93e3ba66-0f9a-4267-95a1-71872f181779	5		10.081481481481482	6.116666666666667	0	0		\N	0	f	0	0.5
522	93e3ba66-0f9a-4267-95a1-71872f181779	6		2.15925925925926	6.031481481481482	0	0		\N	0	f	0	0.5
523	93e3ba66-0f9a-4267-95a1-71872f181779	7		1.9462962962962969	9.907407407407408	0	0		\N	0	f	0	0.5
524	93e3ba66-0f9a-4267-95a1-71872f181779	8		9.996296296296297	9.822222222222223	0	0		\N	0	f	0	0.5
525	93e3ba66-0f9a-4267-95a1-71872f181779	9		18.003703703703703	9.992592592592594	0	0		\N	0	f	0	0.5
526	d2c251b5-9798-40c9-af25-0a8ec2f24833	1		1.9462962962962969	1.942592592592593	0	0		\N	0	f	0	0.5
527	d2c251b5-9798-40c9-af25-0a8ec2f24833	10		17.961111111111112	13.911111111111111	0	0		\N	0	f	0	0.5
528	d2c251b5-9798-40c9-af25-0a8ec2f24833	11		9.911111111111111	13.996296296296297	0	0		\N	0	f	0	0.5
529	d2c251b5-9798-40c9-af25-0a8ec2f24833	12		2.2018518518518526	14.081481481481482	0	0		\N	0	f	0	0.5
530	d2c251b5-9798-40c9-af25-0a8ec2f24833	13		2.074074074074075	18.085185185185185	0	0		\N	0	f	0	0.5
531	d2c251b5-9798-40c9-af25-0a8ec2f24833	14		9.953703703703704	18.085185185185185	0	0		\N	0	f	0	0.5
532	d2c251b5-9798-40c9-af25-0a8ec2f24833	15		17.833333333333332	17.914814814814815	0	0		\N	0	f	0	0.5
533	d2c251b5-9798-40c9-af25-0a8ec2f24833	16		24.05185185185185	15.912962962962963	0	0		\N	0	f	0	0.5
534	d2c251b5-9798-40c9-af25-0a8ec2f24833	17		24.009259259259256	8.331481481481482	0	0		\N	0	f	0	0.5
535	d2c251b5-9798-40c9-af25-0a8ec2f24833	18		23.966666666666665	3.901851851851852	0	0		\N	0	f	0	0.5
536	d2c251b5-9798-40c9-af25-0a8ec2f24833	19		24.09444444444444	12.122222222222224	0	0		\N	0	f	0	0.5
537	d2c251b5-9798-40c9-af25-0a8ec2f24833	2		9.953703703703704	1.9851851851851876	0	0		\N	0	f	0	0.5
538	d2c251b5-9798-40c9-af25-0a8ec2f24833	20		29.929629629629627	13.996296296296297	0	0		\N	0	f	0	0.5
539	d2c251b5-9798-40c9-af25-0a8ec2f24833	21		30.014814814814812	9.992592592592594	0	0		\N	0	f	0	0.5
540	d2c251b5-9798-40c9-af25-0a8ec2f24833	22		29.972222222222218	6.329629629629631	0	0		\N	0	f	0	0.5
541	d2c251b5-9798-40c9-af25-0a8ec2f24833	23		35.89259259259259	9.907407407407408	0	0		\N	0	f	0	0.5
542	d2c251b5-9798-40c9-af25-0a8ec2f24833	3		18.003703703703703	1.9851851851851876	0	0		\N	0	f	0	0.5
543	d2c251b5-9798-40c9-af25-0a8ec2f24833	4		17.918518518518518	6.031481481481482	0	0		\N	0	f	0	0.5
544	d2c251b5-9798-40c9-af25-0a8ec2f24833	5		10.081481481481482	6.116666666666667	0	0		\N	0	f	0	0.5
545	d2c251b5-9798-40c9-af25-0a8ec2f24833	6		2.15925925925926	6.031481481481482	0	0		\N	0	f	0	0.5
546	d2c251b5-9798-40c9-af25-0a8ec2f24833	7		1.9462962962962969	9.907407407407408	0	0		\N	0	f	0	0.5
547	d2c251b5-9798-40c9-af25-0a8ec2f24833	8		9.996296296296297	9.822222222222223	0	0		\N	0	f	0	0.5
548	d2c251b5-9798-40c9-af25-0a8ec2f24833	9		18.003703703703703	9.992592592592594	0	0		\N	0	f	0	0.5
549	bb0dae6d-91cc-417d-9493-08beebeec142	1		1.946	1.943	0	0		\N	0	f	0	0.5
550	bb0dae6d-91cc-417d-9493-08beebeec142	10		17.961	13.911	0	0		\N	0	f	0	0.5
551	bb0dae6d-91cc-417d-9493-08beebeec142	11		9.911	13.996	0	0		\N	0	f	0	0.5
552	bb0dae6d-91cc-417d-9493-08beebeec142	12		2.202	14.081	0	0		\N	0	f	0	0.5
553	bb0dae6d-91cc-417d-9493-08beebeec142	13		2.074	18.085	0	0		\N	0	f	0	0.5
554	bb0dae6d-91cc-417d-9493-08beebeec142	14		9.954	18.085	0	0		\N	0	f	0	0.5
555	bb0dae6d-91cc-417d-9493-08beebeec142	15		17.833	17.915	0	0		\N	0	f	0	0.5
556	bb0dae6d-91cc-417d-9493-08beebeec142	16		24.052	15.913	0	0		\N	0	f	0	0.5
557	bb0dae6d-91cc-417d-9493-08beebeec142	17		24.009	8.331	0	0		\N	0	f	0	0.5
558	bb0dae6d-91cc-417d-9493-08beebeec142	18		23.967	3.902	0	0		\N	0	f	0	0.5
559	bb0dae6d-91cc-417d-9493-08beebeec142	19		24.094	12.122	0	0		\N	0	f	0	0.5
560	bb0dae6d-91cc-417d-9493-08beebeec142	2		9.954	1.985	0	0		\N	0	f	0	0.5
561	bb0dae6d-91cc-417d-9493-08beebeec142	20		29.93	13.996	0	0		\N	0	f	0	0.5
562	bb0dae6d-91cc-417d-9493-08beebeec142	21		30.015	9.993	0	0		\N	0	f	0	0.5
563	bb0dae6d-91cc-417d-9493-08beebeec142	22		29.972	6.33	0	0		\N	0	f	0	0.5
564	bb0dae6d-91cc-417d-9493-08beebeec142	23		35.893	9.907	0	0		\N	0	f	0	0.5
565	bb0dae6d-91cc-417d-9493-08beebeec142	3		18.004	1.985	0	0		\N	0	f	0	0.5
566	bb0dae6d-91cc-417d-9493-08beebeec142	4		17.919	6.031	0	0		\N	0	f	0	0.5
567	bb0dae6d-91cc-417d-9493-08beebeec142	5		10.081	6.117	0	0		\N	0	f	0	0.5
568	bb0dae6d-91cc-417d-9493-08beebeec142	6		2.159	6.031	0	0		\N	0	f	0	0.5
569	bb0dae6d-91cc-417d-9493-08beebeec142	7		1.946	9.907	0	0		\N	0	f	0	0.5
570	bb0dae6d-91cc-417d-9493-08beebeec142	8		9.996	9.822	0	0		\N	0	f	0	0.5
571	bb0dae6d-91cc-417d-9493-08beebeec142	9		18.004	9.993	0	0		\N	0	f	0	0.5
572	703c7452-55bb-4e15-8304-f4e88ddbc2ba	1		14.574074074074074	7.833333333333333	0	0		\N	0	f	0	0.5
573	9a861d33-52f1-4fa1-83d5-76da8fad400a	1		2	2	0	1		\N	0	f	0	0.5
574	9a861d33-52f1-4fa1-83d5-76da8fad400a	10		18	6	0	1		\N	0	f	0	0.5
575	9a861d33-52f1-4fa1-83d5-76da8fad400a	11		2	10	0	3		\N	0	f	0	0.5
576	9a861d33-52f1-4fa1-83d5-76da8fad400a	12		6	10	0	0		\N	0	f	0	0.5
577	9a861d33-52f1-4fa1-83d5-76da8fad400a	13		10	10	0	1		\N	0	f	0	0.5
578	9a861d33-52f1-4fa1-83d5-76da8fad400a	14		14	10	0	0		\N	0	f	0	0.5
579	9a861d33-52f1-4fa1-83d5-76da8fad400a	15		18	10	0	3		\N	0	f	0	0.5
580	9a861d33-52f1-4fa1-83d5-76da8fad400a	16		10	6	0	4		\N	0	f	0	0.5
581	9a861d33-52f1-4fa1-83d5-76da8fad400a	17		14	6	0	0		\N	0	f	0	0.5
582	9a861d33-52f1-4fa1-83d5-76da8fad400a	18		10	10	0	1		\N	0	f	0	0.5
583	9a861d33-52f1-4fa1-83d5-76da8fad400a	19		14	10	0	0		\N	0	f	0	0.5
584	9a861d33-52f1-4fa1-83d5-76da8fad400a	2		6	2	0	0		\N	0	f	0	0.5
585	9a861d33-52f1-4fa1-83d5-76da8fad400a	20		18	10	0	3		\N	0	f	0	0.5
586	9a861d33-52f1-4fa1-83d5-76da8fad400a	3		10	2	0	1		\N	0	f	0	0.5
587	9a861d33-52f1-4fa1-83d5-76da8fad400a	4		14	2	0	0		\N	0	f	0	0.5
588	9a861d33-52f1-4fa1-83d5-76da8fad400a	5		18	2	0	1		\N	0	f	0	0.5
589	9a861d33-52f1-4fa1-83d5-76da8fad400a	6		2	6	0	0		\N	0	f	0	0.5
590	9a861d33-52f1-4fa1-83d5-76da8fad400a	7		6	6	0	0		\N	0	f	0	0.5
591	9a861d33-52f1-4fa1-83d5-76da8fad400a	8		10	6	0	4		\N	0	f	0	0.5
592	9a861d33-52f1-4fa1-83d5-76da8fad400a	9		14	6	0	0		\N	0	f	0	0.5
593	cc51d003-010b-4a2d-8879-f312e80b2cfd	1		2	2	0	1		\N	0	f	0	0.5
594	cc51d003-010b-4a2d-8879-f312e80b2cfd	10		18	6	0	1		\N	0	f	0	0.5
595	cc51d003-010b-4a2d-8879-f312e80b2cfd	11		2	10	0	3		\N	0	f	0	0.5
596	cc51d003-010b-4a2d-8879-f312e80b2cfd	12		6	10	0	0		\N	0	f	0	0.5
597	cc51d003-010b-4a2d-8879-f312e80b2cfd	13		10	10	0	1		\N	0	f	0	0.5
598	cc51d003-010b-4a2d-8879-f312e80b2cfd	14		14	10	0	0		\N	0	f	0	0.5
599	cc51d003-010b-4a2d-8879-f312e80b2cfd	15		18	10	0	3		\N	0	f	0	0.5
600	cc51d003-010b-4a2d-8879-f312e80b2cfd	16		10	6	0	4		\N	0	f	0	0.5
601	cc51d003-010b-4a2d-8879-f312e80b2cfd	17		14	6	0	0		\N	0	f	0	0.5
602	cc51d003-010b-4a2d-8879-f312e80b2cfd	18		10	10	0	1		\N	0	f	0	0.5
603	cc51d003-010b-4a2d-8879-f312e80b2cfd	19		14	10	0	0		\N	0	f	0	0.5
604	cc51d003-010b-4a2d-8879-f312e80b2cfd	2		6	2	0	0		\N	0	f	0	0.5
605	cc51d003-010b-4a2d-8879-f312e80b2cfd	20		18	10	0	3		\N	0	f	0	0.5
606	cc51d003-010b-4a2d-8879-f312e80b2cfd	3		10	2	0	1		\N	0	f	0	0.5
607	cc51d003-010b-4a2d-8879-f312e80b2cfd	4		14	2	0	0		\N	0	f	0	0.5
608	cc51d003-010b-4a2d-8879-f312e80b2cfd	5		18	2	0	1		\N	0	f	0	0.5
609	cc51d003-010b-4a2d-8879-f312e80b2cfd	6		2	6	0	0		\N	0	f	0	0.5
610	cc51d003-010b-4a2d-8879-f312e80b2cfd	7		6	6	0	0		\N	0	f	0	0.5
611	cc51d003-010b-4a2d-8879-f312e80b2cfd	8		10	6	0	4		\N	0	f	0	0.5
612	cc51d003-010b-4a2d-8879-f312e80b2cfd	9		14	6	0	0		\N	0	f	0	0.5
613	cc16078b-cae9-40a3-ad3c-d74da64266f6	1		11.204	6.204	0	0		\N	0	f	0	0.5
614	80	1		11.204	6.204	0	0		\N	0	f	0	0.5
638	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	1	map_demo	1.946	1.943	0	0		\N	0	f	0	0.5
639	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	10	map_demo	17.961	13.911	0	0		\N	0	f	0	0.5
640	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	11	map_demo	9.911	13.996	0	0		\N	0	f	0	0.5
641	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	12	map_demo	2.202	14.081	0	0		\N	0	f	0	0.5
642	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	13	map_demo	2.074	18.085	0	0		\N	0	f	0	0.5
643	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	14	map_demo	9.954	18.085	0	0		\N	0	f	0	0.5
644	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	15	map_demo	17.833	17.915	0	0		\N	0	f	0	0.5
645	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	16	map_demo	24.052	15.913	0	0		\N	0	f	0	0.5
646	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	17	map_demo	24.009	8.331	0	0		\N	0	f	0	0.5
647	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	18	map_demo	23.967	3.902	0	0		\N	0	f	0	0.5
648	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	19	map_demo	24.094	12.122	0	0		\N	0	f	0	0.5
649	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	2	map_demo	9.954	1.985	0	0		\N	0	f	0	0.5
650	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	20	map_demo	29.93	13.996	0	0		\N	0	f	0	0.5
651	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	21	map_demo	30.015	9.993	0	0		\N	0	f	0	0.5
652	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	22	map_demo	29.972	6.33	0	0		\N	0	f	0	0.5
653	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	23	map_demo	35.893	9.907	0	0		\N	0	f	0	0.5
654	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	3	map_demo	18.004	1.985	0	0		\N	0	f	0	0.5
655	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	4	map_demo	17.919	6.031	0	0		\N	0	f	0	0.5
656	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	5	map_demo	10.081	6.117	0	0		\N	0	f	0	0.5
657	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	6	map_demo	2.159	6.031	0	0		\N	0	f	0	0.5
658	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	7	map_demo	1.946	9.907	0	0		\N	0	f	0	0.5
659	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	8	map_demo	9.996	9.822	0	0		\N	0	f	0	0.5
660	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	9	map_demo	18.004	9.993	0	0		\N	0	f	0	0.5
734	1779430599645	14		26	-117	0	0		{"agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
735	1779430599645	16		-154	-117	0	0		{"agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": "", "arrival_action": "wait_user"}	0	f	0	0.5
736	1779430599645	21		-242	-117	0	0		{"agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
737	1779430599645	41		127	-117	0	0		{"agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
738	1779430599645	64		197	-117	0	0		{"bwd_turn": "left", "fwd_turn": "right", "agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
739	1779430599645	74		-320	-117	0	2		{"agvCompat": "RFID", "locationType": "CHARGER", "defaultAction": ""}	0	f	0	0.5
740	1779430599645	84		197	77	0	0		{"agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
741	1779430599645	225		-41	77	0	0		{"agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
742	1779430599645	241		-320	-18	0	0		{"agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
743	1779430599645	264		-320	77	0	0		{"agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
744	1779430599645	999		197	-22	0	0		{"agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
3489	1784004253436	10		5	35	0	2		{"agvCompat": "RFID", "exit_turn": "left", "lidar_off": "yes", "locationType": "CHARGER", "defaultAction": "CHARGE", "exit_reverse_ms": 1000}	0	f	0	0.5
3490	1784004253436	11		5	105	0	0		{"agvCompat": "RFID", "lidar_off": "yes", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
3491	1784004253436	12		245	235	0	8		{"door_id": "gate1", "agvCompat": "RFID", "locationType": "DOOR", "defaultAction": ""}	0	f	0	0.5
3492	1784004253436	13		245	344	0	0		{"turn_map": {"12_14_fwd": "straight", "201_12_fwd": "straight"}, "agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
3493	1784004253436	14		285	475	0	0		{"agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
3494	1784004253436	15		686	475	0	0		{"turn_map": {"104_20_fwd": "left", "104_105_fwd": "straight"}, "agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
3495	1784004253436	16		1103	475	0	0		{"turn_map": {"108_19_fwd": "left", "108_109_fwd": "straight"}, "agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
3496	1784004253436	17		1499	475	0	0		{"turn_map": {"112_18_fwd": "left"}, "agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
3497	1784004253436	18		1499	396	0	0		{"turn_map": {"17_212_fwd": "left"}, "agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
3498	1784004253436	19		1103	396	0	0		{"turn_map": {"16_208_fwd": "left", "209_208_fwd": "straight"}, "agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
3499	1784004253436	20		686	396	0	0		{"turn_map": {"15_204_fwd": "left", "205_204_fwd": "straight"}, "agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
3500	1784004253436	21		5	155	0	8		{"door_id": "gate1", "turn_map": {"11_81_fwd": "left", "81_11_fwd": "right"}, "agvCompat": "RFID", "lidar_off": "yes", "locationType": "DOOR", "defaultAction": ""}	0	f	0	0.5
3501	1784004253436	22		195	155	0	0		{"agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
3502	1784004253436	81		69	155	0	0		{"agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": "", "arrival_action": "wait_user", "trailer_staging": "yes"}	0	f	0	0.5
3503	1784004253436	82		129	155	0	0		{"agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": "", "arrival_action": "wait_user", "trailer_empty_staging": "yes"}	0	f	0	0.5
3504	1784004253436	101		365	475	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "drop", "turn_allowed": "no", "defaultAction": "", "trailer_drop_teams": ["32", "22"]}	0	f	0	0.5
3505	1784004253436	102		445	475	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "drop", "turn_allowed": "no", "defaultAction": "", "trailer_drop_teams": ["33", "23"]}	0	f	0	0.5
3506	1784004253436	103		525	475	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "drop", "turn_allowed": "no", "defaultAction": "", "trailer_drop_teams": ["34", "24"]}	0	f	0	0.5
3507	1784004253436	104		607	475	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "drop", "turn_allowed": "no", "defaultAction": "", "trailer_drop_teams": ["35", "26"]}	0	f	0	0.5
3508	1784004253436	105		765	475	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "drop", "turn_allowed": "no", "defaultAction": "", "trailer_drop_teams": ["36", "25"]}	0	f	0	0.5
3509	1784004253436	106		845	475	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "drop", "turn_allowed": "no", "defaultAction": "", "trailer_drop_teams": ["37", "27"]}	0	f	0	0.5
3510	1784004253436	107		931	475	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "drop", "turn_allowed": "no", "defaultAction": "", "trailer_drop_teams": ["38", "28"]}	0	f	0	0.5
3511	1784004253436	108		1025	475	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "drop", "turn_allowed": "no", "defaultAction": "", "trailer_drop_teams": ["20", "29"]}	0	f	0	0.5
3512	1784004253436	109		1168	475	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "drop", "turn_allowed": "no", "defaultAction": "", "trailer_drop_teams": ["40", "30"]}	0	f	0	0.5
3513	1784004253436	110		1245	475	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "drop", "turn_allowed": "no", "defaultAction": "", "trailer_drop_teams": ["41", "31"]}	0	f	0	0.5
3514	1784004253436	111		1326	475	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "drop", "turn_allowed": "no", "defaultAction": "", "trailer_drop_teams": ["39", "19"]}	0	f	0	0.5
3515	1784004253436	112		1403	475	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "drop", "defaultAction": "", "trailer_drop_teams": ["cb"]}	0	f	0	0.5
3516	1784004253436	201		365	396	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "pickup", "turn_allowed": "no", "defaultAction": "", "trailer_pickup_teams": ["32", "22"]}	0	f	0	0.5
3517	1784004253436	202		445	396	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "pickup", "turn_allowed": "no", "defaultAction": "", "trailer_pickup_teams": ["33", "23"]}	0	f	0	0.5
3518	1784004253436	203		525	396	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "pickup", "turn_allowed": "no", "defaultAction": "", "trailer_pickup_teams": ["34", "24"]}	0	f	0	0.5
3519	1784004253436	204		608	396	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "pickup", "turn_allowed": "no", "defaultAction": "", "trailer_pickup_teams": ["35", "26"]}	0	f	0	0.5
3520	1784004253436	205		765	396	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "pickup", "turn_allowed": "no", "defaultAction": "", "trailer_pickup_teams": ["36", "25"]}	0	f	0	0.5
2332	1779790224391	1		-264	-4	0	0		{"turn_map": {"2_12_bwd": "right", "2_12_fwd": "right", "2_13_bwd": "left", "2_13_fwd": "left", "96_2_bwd": "straight", "96_2_fwd": "straight", "12_13_bwd": "straight", "13_12_fwd": "straight", "96_13_bwd": "right", "96_13_fwd": "left"}, "agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
2333	1779790224391	2		-186	-4	0	0		{"turn_map": {"10_1_bwd": "right", "10_1_fwd": "right", "14_1_fwd": "left", "1_10_bwd": "left", "1_10_fwd": "left", "1_14_bwd": "right", "1_14_fwd": "left", "1_64_bwd": "straight", "1_64_fwd": "straight", "64_1_bwd": "straight", "64_1_fwd": "straight", "10_14_bwd": "straight", "10_64_bwd": "left", "10_64_fwd": "left", "14_10_fwd": "straight", "14_64_fwd": "right", "64_10_bwd": "right", "64_10_fwd": "right", "64_14_bwd": "left", "64_14_fwd": "left"}, "agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
2334	1779790224391	3		-361	-4	0	0		{"turn_map": {"11_96_bwd": "left", "11_96_fwd": "left", "96_11_bwd": "right", "96_11_fwd": "right"}, "agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
2335	1779790224391	4		-17	-4	0	0		{"turn_map": {"18_9_bwd": "right", "18_9_fwd": "right", "19_9_fwd": "left", "9_18_bwd": "left", "9_18_fwd": "left", "9_19_bwd": "right", "9_19_fwd": "right", "16_19_fwd": "straight", "18_19_bwd": "straight", "18_19_fwd": "straight", "19_16_fwd": "straight", "19_18_fwd": "straight"}, "agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
2336	1779790224391	5		148	-4	0	0		{"turn_map": {"17_8_bwd": "right", "17_8_fwd": "right", "18_8_bwd": "left", "18_8_fwd": "left", "8_17_bwd": "left", "8_17_fwd": "left", "8_18_bwd": "right", "8_18_fwd": "right", "17_18_bwd": "straight", "17_18_fwd": "straight", "18_17_bwd": "straight", "18_17_fwd": "straight"}, "agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
2337	1779790224391	6		316	-4	0	0		{"turn_map": {"17_7_bwd": "left", "17_7_fwd": "left", "7_17_bwd": "right", "7_17_fwd": "right"}, "agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
2338	1779790224391	7		316	-85	0	0		{"turn_map": {"16_6_bwd": "right", "16_6_fwd": "right", "6_16_bwd": "left", "6_16_fwd": "left"}, "agvCompat": "RFID", "lidar_off": "yes", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
2339	1779790224391	8		148	-85	0	0		{"turn_map": {"15_5_bwd": "right", "15_5_fwd": "right", "16_5_bwd": "left", "16_5_fwd": "left", "5_15_bwd": "left", "5_15_fwd": "left", "5_16_bwd": "right", "5_16_fwd": "right", "15_16_bwd": "straight", "15_16_fwd": "straight", "16_15_bwd": "straight", "16_15_fwd": "straight"}, "agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
2340	1779790224391	9		-17	-85	0	0		{"turn_map": {"15_4_bwd": "left", "15_4_fwd": "left", "4_15_bwd": "right", "4_15_fwd": "right"}, "agvCompat": "RFID", "lidar_off": "yes", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
2341	1779790224391	10		-186	-85	0	0		{"turn_map": {"2_12_bwd": "left", "2_12_fwd": "left"}, "agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
2342	1779790224391	11		-361	-85	0	0		{"turn_map": {"3_69_bwd": "right", "3_69_fwd": "right", "69_3_bwd": "left", "69_3_fwd": "left"}, "agvCompat": "RFID", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
2343	1779790224391	12		-264	-85	0	0		{"turn_map": {"10_1_bwd": "left", "10_1_fwd": "left", "1_10_bwd": "right", "1_10_fwd": "right", "1_69_bwd": "left", "1_69_fwd": "left", "69_1_bwd": "right", "69_1_fwd": "right", "10_69_bwd": "straight", "10_69_fwd": "straight", "69_10_bwd": "straight", "69_10_fwd": "straight"}, "agvCompat": "RFID", "lidar_off": "yes", "locationType": "NORMAL", "defaultAction": ""}	0	f	0	0.5
2344	1779790224391	13		-264	83	0	2		{"agvCompat": "RFID", "exit_turn": "left", "locationType": "CHARGER", "defaultAction": "", "arrival_action": "wait_charge", "exit_reverse_ms": 1000, "station_agv_type": "trailer"}	0	f	0	0.5
2345	1779790224391	14		-186	80	0	2		{"agvCompat": "RFID", "exit_turn": "left", "locationType": "CHARGER", "defaultAction": "", "arrival_action": "wait_charge", "exit_reverse_ms": 1000, "station_agv_type": "trailer"}	0	f	0	0.5
2346	1779790224391	15		61	-85	0	3		{"team": 1, "agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "pickup", "defaultAction": "PICKUP"}	0	f	0	0.5
2347	1779790224391	16		240	-85	0	3		{"team": 2, "turn_map": {"4_7_fwd": "straight", "7_4_fwd": "straight"}, "agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "pickup", "defaultAction": ""}	0	f	0	0.5
2348	1779790224391	17		240	-4	0	3		{"team": 2, "agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "drop", "defaultAction": ""}	0	f	0	0.5
2349	1779790224391	18		61	-4	0	3		{"team": 1, "agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "drop", "defaultAction": "DROP"}	0	f	0	0.5
2350	1779790224391	19		-80	-4	0	0		{"agvCompat": "RFID", "locationType": "NORMAL", "supply_group": ["1", "4", "5", "6"], "defaultAction": "", "arrival_action": "wait_sys", "trailer_staging": "yes"}	0	f	0	0.5
2351	1779790224391	64		-137	-4	0	0		{"agvCompat": "RFID", "locationType": "NORMAL", "supply_group": ["2", "3"], "defaultAction": "", "arrival_action": "wait_sys"}	0	f	0	0.5
2352	1779790224391	69		-309	-85	0	3		{"team": 3, "turn_map": {"11_12_bwd": "straight", "11_12_fwd": "straight", "12_11_bwd": "straight", "12_11_fwd": "straight"}, "agvCompat": "RFID", "locationType": "DROPOFF", "defaultAction": ""}	0	f	0	0.5
2353	1779790224391	96		-309	-4	0	3		{"team": 5, "turn_map": {"1_3_bwd": "straight", "1_3_fwd": "straight", "3_1_bwd": "straight", "3_1_fwd": "straight"}, "agvCompat": "RFID", "locationType": "DROPOFF", "defaultAction": ""}	0	f	0	0.5
3521	1784004253436	206		845	396	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "pickup", "turn_allowed": "no", "defaultAction": "", "trailer_pickup_teams": ["37", "27"]}	0	f	0	0.5
3522	1784004253436	207		931	396	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "pickup", "turn_allowed": "no", "defaultAction": "", "trailer_pickup_teams": ["38", "28"]}	0	f	0	0.5
3523	1784004253436	208		1025	396	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "pickup", "turn_allowed": "no", "defaultAction": "", "trailer_pickup_teams": ["20", "29"]}	0	f	0	0.5
3524	1784004253436	209		1165	396	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "pickup", "turn_allowed": "no", "defaultAction": "", "trailer_pickup_teams": ["40", "30"]}	0	f	0	0.5
3525	1784004253436	210		1245	396	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "pickup", "turn_allowed": "no", "defaultAction": "", "trailer_pickup_teams": ["41", "31"]}	0	f	0	0.5
3526	1784004253436	211		1326	396	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "pickup", "turn_allowed": "no", "defaultAction": "", "trailer_pickup_teams": ["39", "19"]}	0	f	0	0.5
3527	1784004253436	212		1403	396	0	3		{"agvCompat": "RFID", "locationType": "DROPOFF", "trailer_role": "pickup", "turn_allowed": "no", "defaultAction": "", "trailer_pickup_teams": ["cb"]}	0	f	0	0.5
\.


--
-- Data for Name: agv_map_roads; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agv_map_roads (id, map_id, name, id_source, id_dest, point_start_x, point_start_y, point_end_x, point_end_y, width, speed, move_direction, distance, lidar_off, lidar_off_dir) FROM stdin;
67	56		9	8	0.3227335810661316	13.825260162353516	0.26875752210617065	6.701098918914795	0.3	0.2	0	7.124365714746485	f	none
68	56		8	7	0.26875752210617065	6.701098918914795	0.009482557885348797	-1.2471202611923218	0.3	0.2	0	7.952446896527784	f	none
69	56		7	6	0.009482557885348797	-1.2471202611923218	5.158753871917725	-1.3828330039978027	0.3	0.2	0	5.151059406964406	f	none
70	56		6	5	5.158753871917725	-1.3828330039978027	4.985492706298828	-6.010046482086182	0.3	0.2	0	4.630456133397051	f	none
71	56		5	6	4.985492706298828	-6.010046482086182	5.158753871917725	-1.3828330039978027	0.3	0.2	0	4.630456133397051	f	none
72	56		6	7	5.158753871917725	-1.3828330039978027	0.009482557885348797	-1.2471202611923218	0.3	0.2	0	5.151059406964406	f	none
73	56		7	8	0.009482557885348797	-1.2471202611923218	0.26875752210617065	6.701098918914795	0.3	0.2	0	7.952446896527784	f	none
74	56		8	9	0.26875752210617065	6.701098918914795	0.3227335810661316	13.825260162353516	0.3	0.2	0	7.124365714746485	f	none
75	56		1	2	0.6292698979377747	-10.564980506896973	0.7342950701713562	-8.304348945617676	0.3	0.3	0	2.2630698934533076	f	none
76	56		2	4	0.7342950701713562	-8.304348945617676	0.6464591026306152	-6.204639434814453	0.3	0.3	0	2.101545904079025	f	none
77	56		2	3	0.7342950701713562	-8.304348945617676	-1.9831966161727905	-8.290040016174316	0.3	0.3	0	2.717529357856391	f	none
78	56		3	2	-1.9831966161727905	-8.290040016174316	0.7342950701713562	-8.304348945617676	0.3	0.3	0	2.717529357856391	f	none
79	56		2	1	0.7342950701713562	-8.304348945617676	0.6292698979377747	-10.564980506896973	0.3	0.3	0	2.2630698934533076	f	none
80	56		4	2	0.6464591026306152	-6.204639434814453	0.7342950701713562	-8.304348945617676	0.3	0.3	0	2.101545904079025	f	none
282	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		1	12	7.021	10.01	3.199	13.328	0.95	0.3	0	5.061304970064539	f	none
283	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		12	1	3.199	13.328	7.021	10.01	0.95	0.3	0	5.061304970064539	f	none
284	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		17	2	12.678	15.49	11.167	13.061	0.95	0.3	0	2.860622659492161	f	none
285	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		2	17	11.167	13.061	12.678	15.49	0.95	0.3	0	2.860622659492161	f	none
85	98		1	2	-11.469558715820312	16.204452514648438	-16.930097579956055	17.904834747314453	0.95	0.3	0	5.719159415849774	f	none
86	98		2	1	-16.930097579956055	17.904834747314453	-11.469558715820312	16.204452514648438	0.95	0.3	0	5.719159415849774	f	none
87	98		4	2	-14.501513671875001	15.051336924235025	-16.930097579956055	17.904834747314453	0.95	0.3	0	3.7470614653230983	f	none
88	98		2	4	-16.930097579956055	17.904834747314453	-14.501513671875001	15.051336924235025	0.95	0.3	0	3.7470614653230983	f	none
286	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		2	1	11.167	13.061	7.021	10.01	0.95	0.3	0	5.147612747672459	f	none
287	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		1	2	7.021	10.01	11.167	13.061	0.95	0.3	0	5.147612747672459	f	none
288	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		17	4	12.678	15.49	15.077	17.653	0.95	0.3	0	3.230134672115079	f	none
289	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		4	17	15.077	17.653	12.678	15.49	0.95	0.3	0	3.230134672115079	f	none
290	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		17	16	12.678	15.49	16.618	13.269	0.95	0.3	0	4.522879724246487	f	none
291	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		16	17	16.618	13.269	12.678	15.49	0.95	0.3	0	4.522879724246487	f	none
292	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		16	5	16.618	13.269	18.128	15.224	0.95	0.3	0	2.470247963261989	f	none
293	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		5	16	18.128	15.224	16.618	13.269	0.95	0.3	0	2.470247963261989	f	none
294	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		4	5	15.077	17.653	18.128	15.224	0.95	0.3	0	3.8998258935496075	f	none
295	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		5	4	18.128	15.224	15.077	17.653	0.95	0.3	0	3.8998258935496075	f	none
296	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		5	13	18.128	15.224	18.691	13.417	0.95	0.3	0	1.8926748267993634	f	none
297	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		13	5	18.691	13.417	18.128	15.224	0.95	0.3	0	1.8926748267993634	f	none
298	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		13	14	18.691	13.417	21.12	10.455	0.95	0.3	0	3.8305985172032853	f	none
299	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		14	13	21.12	10.455	18.691	13.417	0.95	0.3	0	3.8305985172032853	f	none
37	97		2	1	-18.949315061188933	8.315894786082202	-18.667470932006836	10.810256958007812	0.3	0.3	0	2.510234801345856	f	none
38	97		1	5	-18.667470932006836	10.810256958007812	-16.24281627556118	8.846178793903523	0.3	0.3	0	3.1203450510696573	f	none
300	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		14	15	21.12	10.455	19.758	8.026	0.95	0.3	0	2.784795324615439	f	none
301	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		15	14	19.758	8.026	21.12	10.455	0.95	0.3	0	2.784795324615439	f	none
302	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		15	16	19.758	8.026	16.618	13.269	0.95	0.3	0	6.111354105269961	f	none
251	59		2	3	10.106666666666666	-0.06791666666667028	7.2799999999999985	-1.1879166666666692	0.3	0.3	0	3.0404678002643677	f	none
252	99		2	21	8.930188630123576	10.74792736740415	14.191511016650526	6.7011891784949915	0.3	0.5	0	6.6375901669616075	f	none
253	99		21	2	14.191511016650526	6.7011891784949915	8.930188630123576	10.74792736740415	0.3	0.5	0	6.6375901669616075	f	none
254	99		2	15	8.930188630123576	10.74792736740415	10.78326822916666	0.9951497395833201	0.3	0.7	0	9.92726424842777	f	none
255	99		14	11	14.191963005065917	0.8172676753997803	15.315471649169922	0.8956514000892639	0.3	0.7	0	1.1262396200066014	f	none
256	99		11	14	15.315471649169922	0.8956514000892639	14.191963005065917	0.8172676753997803	0.3	0.7	0	1.1262396200066014	f	none
257	99		18	2	6.067204258565174	2.434503161276921	8.930188630123576	10.74792736740415	0.3	0.7	0	8.792593561788799	f	none
258	99		2	18	8.930188630123576	10.74792736740415	6.067204258565174	2.434503161276921	0.3	0.75	0	8.792593561788799	f	none
259	99		1	19	7.6451766967773445	-12.51909351348877	8.430276858981415	2.267171856617878	0.3	0.7	0	14.807093768187865	f	none
260	99		19	18	8.430276858981415	2.267171856617878	6.067204258565174	2.434503161276921	0.3	0.7	0	2.3689896328090736	f	none
261	99		19	2	8.430276858981415	2.267171856617878	8.930188630123576	10.74792736740415	0.3	0.7	0	8.495476785481685	f	none
133	87		1	2	-14.587265968322754	-8.011516571044922	-14.66279296875	-5.634148120880127	0.95	0.3	0	2.378567862313896	f	none
134	87		2	3	-14.66279296875	-5.634148120880127	-14.570400047302247	-3.3296561241149902	0.95	0.5	0	2.306343386204279	f	none
135	87		3	4	-14.570400047302247	-3.3296561241149902	-14.478529357910157	0.19267681241035461	0.95	0.5	0	3.523530834163459	f	none
136	87		4	5	-14.478529357910157	0.19267681241035461	-14.385263442993164	3.389639377593994	0.95	0.5	0	3.1983227126215485	f	none
137	87		5	6	-14.385263442993164	3.389639377593994	-14.331920623779297	6.4980244636535645	0.95	0.5	0	3.1088427589055136	f	none
138	87		6	7	-14.331920623779297	6.4980244636535645	-14.249767303466797	8.901872634887695	0.95	0.5	0	2.4052515873363527	f	none
139	87		7	8	-14.249767303466797	8.901872634887695	-14.274264335632324	11.660944938659668	0.925	0.5	0	2.759181052781151	f	none
140	87		8	9	-14.274264335632324	11.660944938659668	-7.6139068603515625	11.903380393981934	0.95	0.5	0	6.664768311691386	f	none
141	87		9	8	-7.6139068603515625	11.903380393981934	-14.274264335632324	11.660944938659668	0.925	0.5	0	6.664768311691386	f	none
142	87		8	7	-14.274264335632324	11.660944938659668	-14.249767303466797	8.901872634887695	0.95	0.5	0	2.759181052781151	f	none
143	87		7	6	-14.249767303466797	8.901872634887695	-14.331920623779297	6.4980244636535645	0.95	0.5	0	2.4052515873363527	f	none
144	87		6	5	-14.331920623779297	6.4980244636535645	-14.385263442993164	3.389639377593994	0.95	0.5	0	3.1088427589055136	f	none
145	87		5	4	-14.385263442993164	3.389639377593994	-14.478529357910157	0.19267681241035461	0.95	0.5	0	3.1983227126215485	f	none
146	87		4	3	-14.478529357910157	0.19267681241035461	-14.570400047302247	-3.3296561241149902	0.975	0.5	0	3.523530834163459	f	none
147	87		3	2	-14.570400047302247	-3.3296561241149902	-14.66279296875	-5.634148120880127	0.95	0.5	0	2.306343386204279	f	none
148	87		2	1	-14.66279296875	-5.634148120880127	-14.587265968322754	-8.011516571044922	0.95	0.3	0	2.378567862313896	f	none
303	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		16	15	16.618	13.269	19.758	8.026	0.95	0.3	0	6.111354105269961	f	none
304	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		10	12	3.999	15.787	3.199	13.328	0.95	0.3	0	2.585861751911731	f	none
305	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		12	10	3.199	13.328	3.999	15.787	0.95	0.3	0	2.585861751911731	f	none
306	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		16	13	16.618	13.269	18.691	13.417	0.95	0.3	0	2.078276449368563	f	none
307	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		13	16	18.691	13.417	16.618	13.269	0.95	0.3	0	2.078276449368563	f	none
308	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		13	15	18.691	13.417	19.758	8.026	0.95	0.3	0	5.495577312712469	f	none
309	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		15	13	19.758	8.026	18.691	13.417	0.95	0.3	0	5.495577312712469	f	none
310	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		14	16	21.12	10.455	16.618	13.269	0.95	0.3	0	5.309105386032568	f	none
311	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		16	14	16.618	13.269	21.12	10.455	0.95	0.3	0	5.309105386032568	f	none
312	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		4	6	15.077	17.653	18.04	19.933	0.95	0.3	0	3.7386854641705285	f	none
313	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		6	4	18.04	19.933	15.077	17.653	0.95	0.3	0	3.7386854641705285	f	none
314	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		5	6	18.128	15.224	18.04	19.933	0.95	0.3	0	4.709822183479966	f	none
315	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		6	5	18.04	19.933	18.128	15.224	0.95	0.3	0	4.709822183479966	f	none
316	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		7	3	10.486	19.637	11.049	17.149	0.95	0.3	0	2.550904349441585	f	none
317	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		3	7	11.049	17.149	10.486	19.637	0.95	0.3	0	2.550904349441585	f	none
318	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		6	7	18.04	19.933	10.486	19.637	0.95	0.3	0	7.559797087223967	f	none
319	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		7	6	10.486	19.637	18.04	19.933	0.95	0.3	0	7.559797087223967	f	none
320	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		3	4	11.049	17.149	15.077	17.653	0.95	0.3	0	4.059408823954542	f	none
321	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		4	3	15.077	17.653	11.049	17.149	0.95	0.3	0	4.059408823954542	f	none
322	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		7	9	10.486	19.637	5.184	21.029	0.95	0.3	0	5.481684777511381	f	none
323	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		9	7	5.184	21.029	10.486	19.637	0.95	0.3	0	5.481684777511381	f	none
324	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		8	9	6.961	18.452	5.184	21.029	0.95	0.3	0	3.130280818073674	f	none
325	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		9	8	5.184	21.029	6.961	18.452	0.95	0.3	0	3.130280818073674	f	none
326	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		11	1	6.784	14.809	7.021	10.01	0.95	0.3	0	4.804848592827874	f	none
327	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		1	11	7.021	10.01	6.784	14.809	0.95	0.3	0	4.804848592827874	f	none
328	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		8	7	6.961	18.452	10.486	19.637	0.95	0.3	0	3.7188506288905985	f	none
329	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		7	8	10.486	19.637	6.961	18.452	0.95	0.3	0	3.7188506288905985	f	none
330	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		22	12	3.051	8.144	3.199	13.328	0.95	0.3	0	5.1861122240074975	f	none
331	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		12	22	3.199	13.328	3.051	8.144	0.95	0.3	0	5.1861122240074975	f	none
332	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		22	1	3.051	8.144	7.021	10.01	0.95	0.3	0	4.386667983789062	f	none
333	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		1	22	7.021	10.01	3.051	8.144	0.95	0.3	0	4.386667983789062	f	none
334	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		22	21	3.051	8.144	4.177	4.708	0.95	0.3	0	3.615794795062352	f	none
335	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		21	22	4.177	4.708	3.051	8.144	0.95	0.3	0	3.615794795062352	f	none
336	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		21	23	4.177	4.708	12.797	7.493	0.95	0.3	0	9.058731975282193	f	none
337	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		23	21	12.797	7.493	4.177	4.708	0.95	0.3	0	9.058731975282193	f	none
338	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		23	18	12.797	7.493	11.612	3.879	0.95	0.3	0	3.803317104844139	f	none
339	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		18	23	11.612	3.879	12.797	7.493	0.95	0.3	0	3.803317104844139	f	none
340	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		18	19	11.612	3.879	16.262	3.731	0.95	0.3	0	4.652354672636213	f	none
341	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		19	18	16.262	3.731	11.612	3.879	0.95	0.3	0	4.652354672636213	f	none
342	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		19	20	16.262	3.731	21.861	4.205	0.95	0.3	0	5.619028118812007	f	none
343	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		20	19	21.861	4.205	16.262	3.731	0.95	0.3	0	5.619028118812007	f	none
344	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		20	15	21.861	4.205	19.758	8.026	0.95	0.3	0	4.361496302875884	f	none
262	99		2	19	8.930188630123576	10.74792736740415	8.430276858981415	2.267171856617878	0.3	0.7	0	8.495476785481685	f	none
263	99		19	1	8.430276858981415	2.267171856617878	7.6451766967773445	-12.51909351348877	0.975	0.7	0	14.807093768187865	f	none
264	99		18	19	6.067204258565174	2.434503161276921	8.430276858981415	2.267171856617878	0.3	0.7	0	2.3689896328090736	f	none
265	99		18	20	6.067204258565174	2.434503161276921	5.991900529882409	0.045537442879473033	0.3	0.5	0	2.390152266118576	f	none
266	99		20	18	5.991900529882409	0.045537442879473033	6.067204258565174	2.434503161276921	0.3	0.5	0	2.390152266118576	f	none
267	99		2	3	8.930188630123576	10.74792736740415	19.9162094674884	10.3946839689834	0.95	0.75	0	10.991698446443204	f	none
268	99		8	10	14.610569686889658	-10.163110898335777	27.79301643371582	-11.047908782958984	0.3	0.5	0	13.212106929991952	f	none
269	99		10	8	27.79301643371582	-11.047908782958984	14.610569686889658	-10.163110898335777	0.3	0.5	0	13.212106929991952	f	none
270	99		8	11	14.610569686889658	-10.163110898335777	15.315471649169922	0.8956514000892639	0.3	0.5	0	11.081205275126601	f	none
271	99		11	8	15.315471649169922	0.8956514000892639	14.610569686889658	-10.163110898335777	0.3	0.5	0	11.081205275126601	f	none
272	99		3	4	19.9162094674884	10.3946839689834	19.57169264444009	-0.741306406763161	0.95	0.5	0	11.141318301264144	f	none
273	99		4	3	19.57169264444009	-0.741306406763161	19.9162094674884	10.3946839689834	0.925	0.5	0	11.141318301264144	f	none
274	99		3	2	19.9162094674884	10.3946839689834	8.930188630123576	10.74792736740415	0.925	0.75	0	10.991698446443204	f	none
275	99		4	5	19.57169264444009	-0.741306406763161	17.829244613647457	-7.077150090535475	0.925	0.5	0	6.57107604013305	f	none
276	99		5	4	17.829244613647457	-7.077150090535475	19.57169264444009	-0.741306406763161	0.95	0.5	0	6.57107604013305	f	none
277	99		6	7	22.95619773864746	-12.285483423868811	27.51348940531413	-13.424806340535476	0.95	0.5	0	4.697548727103452	f	none
278	99		7	6	27.51348940531413	-13.424806340535476	22.95619773864746	-12.285483423868811	0.975	0.5	0	4.697548727103452	f	none
279	99		14	15	14.191963005065917	0.8172676753997803	10.78326822916666	0.9951497395833201	0.3	0.7	0	3.4133329904949337	f	none
280	99		15	14	10.78326822916666	0.9951497395833201	14.191963005065917	0.8172676753997803	0.3	0.7	0	3.4133329904949337	f	none
281	99		15	2	10.78326822916666	0.9951497395833201	8.930188630123576	10.74792736740415	0.3	0.7	0	9.92726424842777	f	none
345	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		15	20	19.758	8.026	21.861	4.205	0.95	0.3	0	4.361496302875884	f	none
346	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		15	19	19.758	8.026	16.262	3.731	0.95	0.3	0	5.537963614903947	f	none
347	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		19	15	16.262	3.731	19.758	8.026	0.95	0.3	0	5.537963614903947	f	none
348	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		11	2	6.784	14.809	11.167	13.061	0.95	0.3	0	4.718706708410685	f	none
349	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		2	11	11.167	13.061	6.784	14.809	0.95	0.3	0	4.718706708410685	f	none
350	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		19	23	16.262	3.731	12.797	7.493	0.95	0.3	0	5.114574175823439	f	none
351	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		23	19	12.797	7.493	16.262	3.731	0.95	0.3	0	5.114574175823439	f	none
352	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		23	16	12.797	7.493	16.618	13.269	0.95	0.3	0	6.925475940323523	f	none
353	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		16	23	16.618	13.269	12.797	7.493	0.95	0.3	0	6.925475940323523	f	none
354	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		1	23	7.021	10.01	12.797	7.493	0.95	0.3	0	6.300592432462205	f	none
355	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		23	1	12.797	7.493	7.021	10.01	0.95	0.3	0	6.300592432462205	f	none
356	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		24	25	10.111	7.978	20.094	19.948	0.95	0.3	0	15.586570790266858	f	none
357	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		25	24	20.094	19.948	10.111	7.978	0.95	0.3	0	15.586570790266858	f	none
358	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		25	26	20.094	19.948	24.678	13.225	0.95	0.3	0	8.13706243063183	f	none
359	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		26	25	24.678	13.225	20.094	19.948	0.95	0.3	0	8.13706243063183	f	none
360	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		26	27	24.678	13.225	25.086	7.112	0.95	0.3	0	6.126600443965641	f	none
361	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		27	26	25.086	7.112	24.678	13.225	0.95	0.3	0	6.126600443965641	f	none
362	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		24	27	10.111	7.978	25.086	7.112	0.95	0.3	0	15.000019366654163	f	none
363	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		27	24	25.086	7.112	10.111	7.978	0.95	0.3	0	15.000019366654163	f	none
364	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		24	26	10.111	7.978	24.678	13.225	0.95	0.3	0	15.483168215840065	f	none
365	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		26	24	24.678	13.225	10.111	7.978	0.95	0.3	0	15.483168215840065	f	none
366	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		25	28	20.094	19.948	39.972	17.083	0.95	0.3	0	20.083403820069943	f	none
367	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		28	25	39.972	17.083	20.094	19.948	0.95	0.3	0	20.083403820069943	f	none
368	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		10	8	3.999	15.787	6.961	18.452	0.95	0.3	0	3.9844283153295663	f	none
369	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		8	10	6.961	18.452	3.999	15.787	0.95	0.3	0	3.9844283153295663	f	none
370	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		28	27	39.972	17.083	25.086	7.112	0.95	0.3	0	17.916859016021753	f	none
371	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		27	28	25.086	7.112	39.972	17.083	0.95	0.3	0	17.916859016021753	f	none
372	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		26	28	24.678	13.225	39.972	17.083	0.95	0.3	0	15.773097349601315	f	none
373	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		28	26	39.972	17.083	24.678	13.225	0.95	0.3	0	15.773097349601315	f	none
374	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		11	10	6.784	14.809	3.999	15.787	0.95	0.3	0	2.951729831810493	f	none
375	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		10	11	3.999	15.787	6.784	14.809	0.95	0.3	0	2.951729831810493	f	none
376	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		8	3	6.961	18.452	11.049	17.149	0.95	0.3	0	4.290635500715482	f	none
377	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		3	8	11.049	17.149	6.961	18.452	0.95	0.3	0	4.290635500715482	f	none
378	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		11	3	6.784	14.809	11.049	17.149	0.95	0.3	0	4.864753333931743	f	none
379	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		3	11	11.049	17.149	6.784	14.809	0.95	0.3	0	4.864753333931743	f	none
380	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		3	17	11.049	17.149	12.678	15.49	0.95	0.3	0	2.3250638700904553	f	none
381	d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce		17	3	12.678	15.49	11.049	17.149	0.95	0.3	0	2.3250638700904553	f	none
382	4001ae10-9a25-4f79-9941-6bfc467df987		1	2	2	2	6	2	0.95	0.3	0	4	f	none
383	4001ae10-9a25-4f79-9941-6bfc467df987		2	1	6	2	2	2	0.95	0.3	0	4	f	none
384	4001ae10-9a25-4f79-9941-6bfc467df987		12	13	6	10	10	10	0.95	0.3	0	4	f	none
385	4001ae10-9a25-4f79-9941-6bfc467df987		13	12	10	10	6	10	0.95	0.3	0	4	f	none
386	4001ae10-9a25-4f79-9941-6bfc467df987		13	14	10	10	14	10	0.95	0.3	0	4	f	none
387	4001ae10-9a25-4f79-9941-6bfc467df987		14	13	14	10	10	10	0.95	0.3	0	4	f	none
388	4001ae10-9a25-4f79-9941-6bfc467df987		14	15	14	10	18	10	0.95	0.3	0	4	f	none
389	4001ae10-9a25-4f79-9941-6bfc467df987		15	14	18	10	14	10	0.95	0.3	0	4	f	none
390	4001ae10-9a25-4f79-9941-6bfc467df987		1	6	2	2	2	6	0.95	0.3	0	4	f	none
391	4001ae10-9a25-4f79-9941-6bfc467df987		6	1	2	6	2	2	0.95	0.3	0	4	f	none
392	4001ae10-9a25-4f79-9941-6bfc467df987		6	11	2	6	2	10	0.95	0.3	0	4	f	none
393	4001ae10-9a25-4f79-9941-6bfc467df987		11	6	2	10	2	6	0.95	0.3	0	4	f	none
394	4001ae10-9a25-4f79-9941-6bfc467df987		2	7	6	2	6	6	0.95	0.3	0	4	f	none
395	4001ae10-9a25-4f79-9941-6bfc467df987		7	2	6	6	6	2	0.95	0.3	0	4	f	none
396	4001ae10-9a25-4f79-9941-6bfc467df987		7	12	6	6	6	10	0.95	0.3	0	4	f	none
397	4001ae10-9a25-4f79-9941-6bfc467df987		12	7	6	10	6	6	0.95	0.3	0	4	f	none
398	4001ae10-9a25-4f79-9941-6bfc467df987		3	8	10	2	10	6	0.95	0.3	0	4	f	none
399	4001ae10-9a25-4f79-9941-6bfc467df987		8	3	10	6	10	2	0.95	0.3	0	4	f	none
400	4001ae10-9a25-4f79-9941-6bfc467df987		8	13	10	6	10	10	0.95	0.3	0	4	f	none
401	4001ae10-9a25-4f79-9941-6bfc467df987		13	8	10	10	10	6	0.95	0.3	0	4	f	none
402	4001ae10-9a25-4f79-9941-6bfc467df987		4	9	14	2	14	6	0.95	0.3	0	4	f	none
403	4001ae10-9a25-4f79-9941-6bfc467df987		9	4	14	6	14	2	0.95	0.3	0	4	f	none
404	4001ae10-9a25-4f79-9941-6bfc467df987		2	3	6	2	10	2	0.95	0.3	0	4	f	none
405	4001ae10-9a25-4f79-9941-6bfc467df987		3	2	10	2	6	2	0.95	0.3	0	4	f	none
406	4001ae10-9a25-4f79-9941-6bfc467df987		9	14	14	6	14	10	0.95	0.3	0	4	f	none
407	4001ae10-9a25-4f79-9941-6bfc467df987		14	9	14	10	14	6	0.95	0.3	0	4	f	none
408	4001ae10-9a25-4f79-9941-6bfc467df987		5	10	18	2	18	6	0.95	0.3	0	4	f	none
409	4001ae10-9a25-4f79-9941-6bfc467df987		10	5	18	6	18	2	0.95	0.3	0	4	f	none
410	4001ae10-9a25-4f79-9941-6bfc467df987		10	15	18	6	18	10	0.95	0.3	0	4	f	none
411	4001ae10-9a25-4f79-9941-6bfc467df987		15	10	18	10	18	6	0.95	0.3	0	4	f	none
412	4001ae10-9a25-4f79-9941-6bfc467df987		16	17	10	6	14	6	0.95	0.3	0	4	f	none
413	4001ae10-9a25-4f79-9941-6bfc467df987		17	16	14	6	10	6	0.95	0.3	0	4	f	none
414	4001ae10-9a25-4f79-9941-6bfc467df987		16	18	10	6	10	10	0.95	0.3	0	4	f	none
415	4001ae10-9a25-4f79-9941-6bfc467df987		18	16	10	10	10	6	0.95	0.3	0	4	f	none
416	4001ae10-9a25-4f79-9941-6bfc467df987		18	19	10	10	14	10	0.95	0.3	0	4	f	none
417	4001ae10-9a25-4f79-9941-6bfc467df987		19	18	14	10	10	10	0.95	0.3	0	4	f	none
418	4001ae10-9a25-4f79-9941-6bfc467df987		19	20	14	10	18	10	0.95	0.3	0	4	f	none
419	4001ae10-9a25-4f79-9941-6bfc467df987		20	19	18	10	14	10	0.95	0.3	0	4	f	none
420	4001ae10-9a25-4f79-9941-6bfc467df987		17	19	14	6	14	10	0.95	0.3	0	4	f	none
421	4001ae10-9a25-4f79-9941-6bfc467df987		19	17	14	10	14	6	0.95	0.3	0	4	f	none
422	4001ae10-9a25-4f79-9941-6bfc467df987		3	4	10	2	14	2	0.95	0.3	0	4	f	none
423	4001ae10-9a25-4f79-9941-6bfc467df987		4	3	14	2	10	2	0.95	0.3	0	4	f	none
424	4001ae10-9a25-4f79-9941-6bfc467df987		4	5	14	2	18	2	0.95	0.3	0	4	f	none
425	4001ae10-9a25-4f79-9941-6bfc467df987		5	4	18	2	14	2	0.95	0.3	0	4	f	none
426	4001ae10-9a25-4f79-9941-6bfc467df987		6	7	2	6	6	6	0.95	0.3	0	4	f	none
427	4001ae10-9a25-4f79-9941-6bfc467df987		7	6	6	6	2	6	0.95	0.3	0	4	f	none
428	4001ae10-9a25-4f79-9941-6bfc467df987		7	8	6	6	10	6	0.95	0.3	0	4	f	none
429	4001ae10-9a25-4f79-9941-6bfc467df987		8	7	10	6	6	6	0.95	0.3	0	4	f	none
430	4001ae10-9a25-4f79-9941-6bfc467df987		8	9	10	6	14	6	0.95	0.3	0	4	f	none
431	4001ae10-9a25-4f79-9941-6bfc467df987		9	8	14	6	10	6	0.95	0.3	0	4	f	none
432	4001ae10-9a25-4f79-9941-6bfc467df987		9	10	14	6	18	6	0.95	0.3	0	4	f	none
433	4001ae10-9a25-4f79-9941-6bfc467df987		10	9	18	6	14	6	0.95	0.3	0	4	f	none
434	4001ae10-9a25-4f79-9941-6bfc467df987		11	12	2	10	6	10	0.95	0.3	0	4	f	none
435	4001ae10-9a25-4f79-9941-6bfc467df987		12	11	6	10	2	10	0.95	0.3	0	4	f	none
436	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		1	2	2	2	6	2	0.95	0.3	0	4	f	none
437	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		2	1	6	2	2	2	0.95	0.3	0	4	f	none
438	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		12	13	6	10	10	10	0.95	0.3	0	4	f	none
439	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		13	12	10	10	6	10	0.95	0.3	0	4	f	none
440	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		13	14	10	10	14	10	0.95	0.3	0	4	f	none
441	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		14	13	14	10	10	10	0.95	0.3	0	4	f	none
442	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		14	15	14	10	18	10	0.95	0.3	0	4	f	none
443	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		15	14	18	10	14	10	0.95	0.3	0	4	f	none
444	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		1	6	2	2	2	6	0.95	0.3	0	4	f	none
445	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		6	1	2	6	2	2	0.95	0.3	0	4	f	none
446	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		6	11	2	6	2	10	0.95	0.3	0	4	f	none
447	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		11	6	2	10	2	6	0.95	0.3	0	4	f	none
448	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		2	7	6	2	6	6	0.95	0.3	0	4	f	none
449	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		7	2	6	6	6	2	0.95	0.3	0	4	f	none
450	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		7	12	6	6	6	10	0.95	0.3	0	4	f	none
451	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		12	7	6	10	6	6	0.95	0.3	0	4	f	none
452	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		3	8	10	2	10	6	0.95	0.3	0	4	f	none
453	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		8	3	10	6	10	2	0.95	0.3	0	4	f	none
454	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		8	13	10	6	10	10	0.95	0.3	0	4	f	none
455	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		13	8	10	10	10	6	0.95	0.3	0	4	f	none
456	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		4	9	14	2	14	6	0.95	0.3	0	4	f	none
457	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		9	4	14	6	14	2	0.95	0.3	0	4	f	none
458	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		2	3	6	2	10	2	0.95	0.3	0	4	f	none
459	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		3	2	10	2	6	2	0.95	0.3	0	4	f	none
460	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		9	14	14	6	14	10	0.95	0.3	0	4	f	none
461	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		14	9	14	10	14	6	0.95	0.3	0	4	f	none
462	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		5	10	18	2	18	6	0.95	0.3	0	4	f	none
463	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		10	5	18	6	18	2	0.95	0.3	0	4	f	none
464	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		10	15	18	6	18	10	0.95	0.3	0	4	f	none
465	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		15	10	18	10	18	6	0.95	0.3	0	4	f	none
466	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		16	17	10	6	14	6	0.95	0.3	0	4	f	none
467	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		17	16	14	6	10	6	0.95	0.3	0	4	f	none
468	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		16	18	10	6	10	10	0.95	0.3	0	4	f	none
469	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		18	16	10	10	10	6	0.95	0.3	0	4	f	none
470	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		18	19	10	10	14	10	0.95	0.3	0	4	f	none
471	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		19	18	14	10	10	10	0.95	0.3	0	4	f	none
472	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		19	20	14	10	18	10	0.95	0.3	0	4	f	none
473	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		20	19	18	10	14	10	0.95	0.3	0	4	f	none
474	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		17	19	14	6	14	10	0.95	0.3	0	4	f	none
475	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		19	17	14	10	14	6	0.95	0.3	0	4	f	none
476	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		3	4	10	2	14	2	0.95	0.3	0	4	f	none
477	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		4	3	14	2	10	2	0.95	0.3	0	4	f	none
478	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		4	5	14	2	18	2	0.95	0.3	0	4	f	none
479	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		5	4	18	2	14	2	0.95	0.3	0	4	f	none
480	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		6	7	2	6	6	6	0.95	0.3	0	4	f	none
481	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		7	6	6	6	2	6	0.95	0.3	0	4	f	none
482	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		7	8	6	6	10	6	0.95	0.3	0	4	f	none
483	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		8	7	10	6	6	6	0.95	0.3	0	4	f	none
484	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		8	9	10	6	14	6	0.95	0.3	0	4	f	none
485	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		9	8	14	6	10	6	0.95	0.3	0	4	f	none
486	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		9	10	14	6	18	6	0.95	0.3	0	4	f	none
487	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		10	9	18	6	14	6	0.95	0.3	0	4	f	none
488	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		11	12	2	10	6	10	0.95	0.3	0	4	f	none
489	abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8		12	11	6	10	2	10	0.95	0.3	0	4	f	none
490	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		1	2	2	2	6	2	0.95	0.3	0	4	f	none
491	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		2	1	6	2	2	2	0.95	0.3	0	4	f	none
492	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		12	13	6	10	10	10	0.95	0.3	0	4	f	none
493	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		13	12	10	10	6	10	0.95	0.3	0	4	f	none
494	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		13	14	10	10	14	10	0.95	0.3	0	4	f	none
495	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		14	13	14	10	10	10	0.95	0.3	0	4	f	none
496	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		14	15	14	10	18	10	0.95	0.3	0	4	f	none
497	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		15	14	18	10	14	10	0.95	0.3	0	4	f	none
498	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		1	6	2	2	2	6	0.95	0.3	0	4	f	none
499	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		6	1	2	6	2	2	0.95	0.3	0	4	f	none
500	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		6	11	2	6	2	10	0.95	0.3	0	4	f	none
501	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		11	6	2	10	2	6	0.95	0.3	0	4	f	none
502	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		2	7	6	2	6	6	0.95	0.3	0	4	f	none
503	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		7	2	6	6	6	2	0.95	0.3	0	4	f	none
504	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		7	12	6	6	6	10	0.95	0.3	0	4	f	none
505	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		12	7	6	10	6	6	0.95	0.3	0	4	f	none
506	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		3	8	10	2	10	6	0.95	0.3	0	4	f	none
507	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		8	3	10	6	10	2	0.95	0.3	0	4	f	none
508	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		8	13	10	6	10	10	0.95	0.3	0	4	f	none
509	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		13	8	10	10	10	6	0.95	0.3	0	4	f	none
510	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		4	9	14	2	14	6	0.95	0.3	0	4	f	none
511	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		9	4	14	6	14	2	0.95	0.3	0	4	f	none
512	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		2	3	6	2	10	2	0.95	0.3	0	4	f	none
513	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		3	2	10	2	6	2	0.95	0.3	0	4	f	none
514	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		9	14	14	6	14	10	0.95	0.3	0	4	f	none
515	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		14	9	14	10	14	6	0.95	0.3	0	4	f	none
516	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		5	10	18	2	18	6	0.95	0.3	0	4	f	none
517	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		10	5	18	6	18	2	0.95	0.3	0	4	f	none
518	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		10	15	18	6	18	10	0.95	0.3	0	4	f	none
519	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		15	10	18	10	18	6	0.95	0.3	0	4	f	none
520	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		16	17	10	6	14	6	0.95	0.3	0	4	f	none
521	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		17	16	14	6	10	6	0.95	0.3	0	4	f	none
522	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		16	18	10	6	10	10	0.95	0.3	0	4	f	none
523	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		18	16	10	10	10	6	0.95	0.3	0	4	f	none
524	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		18	19	10	10	14	10	0.95	0.3	0	4	f	none
525	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		19	18	14	10	10	10	0.95	0.3	0	4	f	none
526	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		19	20	14	10	18	10	0.95	0.3	0	4	f	none
527	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		20	19	18	10	14	10	0.95	0.3	0	4	f	none
528	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		17	19	14	6	14	10	0.95	0.3	0	4	f	none
529	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		19	17	14	10	14	6	0.95	0.3	0	4	f	none
530	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		3	4	10	2	14	2	0.95	0.3	0	4	f	none
531	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		4	3	14	2	10	2	0.95	0.3	0	4	f	none
532	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		4	5	14	2	18	2	0.95	0.3	0	4	f	none
533	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		5	4	18	2	14	2	0.95	0.3	0	4	f	none
534	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		6	7	2	6	6	6	0.95	0.3	0	4	f	none
535	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		7	6	6	6	2	6	0.95	0.3	0	4	f	none
536	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		7	8	6	6	10	6	0.95	0.3	0	4	f	none
537	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		8	7	10	6	6	6	0.95	0.3	0	4	f	none
538	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		8	9	10	6	14	6	0.95	0.3	0	4	f	none
539	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		9	8	14	6	10	6	0.95	0.3	0	4	f	none
540	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		9	10	14	6	18	6	0.95	0.3	0	4	f	none
541	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		10	9	18	6	14	6	0.95	0.3	0	4	f	none
542	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		11	12	2	10	6	10	0.95	0.3	0	4	f	none
543	97c66d8a-21f3-4a42-ba5c-295bd62bdfc0		12	11	6	10	2	10	0.95	0.3	0	4	f	none
544	4656f23b-ed40-43d1-a314-94bbdedf5d29		1	2	2	2	6	2	0.95	0.3	0	4	f	none
545	4656f23b-ed40-43d1-a314-94bbdedf5d29		2	1	6	2	2	2	0.95	0.3	0	4	f	none
546	4656f23b-ed40-43d1-a314-94bbdedf5d29		12	13	6	10	10	10	0.95	0.3	0	4	f	none
547	4656f23b-ed40-43d1-a314-94bbdedf5d29		13	12	10	10	6	10	0.95	0.3	0	4	f	none
548	4656f23b-ed40-43d1-a314-94bbdedf5d29		13	14	10	10	14	10	0.95	0.3	0	4	f	none
549	4656f23b-ed40-43d1-a314-94bbdedf5d29		14	13	14	10	10	10	0.95	0.3	0	4	f	none
550	4656f23b-ed40-43d1-a314-94bbdedf5d29		14	15	14	10	18	10	0.95	0.3	0	4	f	none
551	4656f23b-ed40-43d1-a314-94bbdedf5d29		15	14	18	10	14	10	0.95	0.3	0	4	f	none
552	4656f23b-ed40-43d1-a314-94bbdedf5d29		1	6	2	2	2	6	0.95	0.3	0	4	f	none
553	4656f23b-ed40-43d1-a314-94bbdedf5d29		6	1	2	6	2	2	0.95	0.3	0	4	f	none
554	4656f23b-ed40-43d1-a314-94bbdedf5d29		6	11	2	6	2	10	0.95	0.3	0	4	f	none
555	4656f23b-ed40-43d1-a314-94bbdedf5d29		11	6	2	10	2	6	0.95	0.3	0	4	f	none
556	4656f23b-ed40-43d1-a314-94bbdedf5d29		2	7	6	2	6	6	0.95	0.3	0	4	f	none
557	4656f23b-ed40-43d1-a314-94bbdedf5d29		7	2	6	6	6	2	0.95	0.3	0	4	f	none
558	4656f23b-ed40-43d1-a314-94bbdedf5d29		7	12	6	6	6	10	0.95	0.3	0	4	f	none
559	4656f23b-ed40-43d1-a314-94bbdedf5d29		12	7	6	10	6	6	0.95	0.3	0	4	f	none
560	4656f23b-ed40-43d1-a314-94bbdedf5d29		3	8	10	2	10	6	0.95	0.3	0	4	f	none
561	4656f23b-ed40-43d1-a314-94bbdedf5d29		8	3	10	6	10	2	0.95	0.3	0	4	f	none
562	4656f23b-ed40-43d1-a314-94bbdedf5d29		8	13	10	6	10	10	0.95	0.3	0	4	f	none
563	4656f23b-ed40-43d1-a314-94bbdedf5d29		13	8	10	10	10	6	0.95	0.3	0	4	f	none
564	4656f23b-ed40-43d1-a314-94bbdedf5d29		4	9	14	2	14	6	0.95	0.3	0	4	f	none
565	4656f23b-ed40-43d1-a314-94bbdedf5d29		9	4	14	6	14	2	0.95	0.3	0	4	f	none
566	4656f23b-ed40-43d1-a314-94bbdedf5d29		2	3	6	2	10	2	0.95	0.3	0	4	f	none
567	4656f23b-ed40-43d1-a314-94bbdedf5d29		3	2	10	2	6	2	0.95	0.3	0	4	f	none
568	4656f23b-ed40-43d1-a314-94bbdedf5d29		9	14	14	6	14	10	0.95	0.3	0	4	f	none
569	4656f23b-ed40-43d1-a314-94bbdedf5d29		14	9	14	10	14	6	0.95	0.3	0	4	f	none
570	4656f23b-ed40-43d1-a314-94bbdedf5d29		5	10	18	2	18	6	0.95	0.3	0	4	f	none
571	4656f23b-ed40-43d1-a314-94bbdedf5d29		10	5	18	6	18	2	0.95	0.3	0	4	f	none
572	4656f23b-ed40-43d1-a314-94bbdedf5d29		10	15	18	6	18	10	0.95	0.3	0	4	f	none
573	4656f23b-ed40-43d1-a314-94bbdedf5d29		15	10	18	10	18	6	0.95	0.3	0	4	f	none
574	4656f23b-ed40-43d1-a314-94bbdedf5d29		16	17	10	6	14	6	0.95	0.3	0	4	f	none
575	4656f23b-ed40-43d1-a314-94bbdedf5d29		17	16	14	6	10	6	0.95	0.3	0	4	f	none
576	4656f23b-ed40-43d1-a314-94bbdedf5d29		16	18	10	6	10	10	0.95	0.3	0	4	f	none
577	4656f23b-ed40-43d1-a314-94bbdedf5d29		18	16	10	10	10	6	0.95	0.3	0	4	f	none
578	4656f23b-ed40-43d1-a314-94bbdedf5d29		18	19	10	10	14	10	0.95	0.3	0	4	f	none
579	4656f23b-ed40-43d1-a314-94bbdedf5d29		19	18	14	10	10	10	0.95	0.3	0	4	f	none
580	4656f23b-ed40-43d1-a314-94bbdedf5d29		19	20	14	10	18	10	0.95	0.3	0	4	f	none
581	4656f23b-ed40-43d1-a314-94bbdedf5d29		20	19	18	10	14	10	0.95	0.3	0	4	f	none
582	4656f23b-ed40-43d1-a314-94bbdedf5d29		17	19	14	6	14	10	0.95	0.3	0	4	f	none
583	4656f23b-ed40-43d1-a314-94bbdedf5d29		19	17	14	10	14	6	0.95	0.3	0	4	f	none
584	4656f23b-ed40-43d1-a314-94bbdedf5d29		3	4	10	2	14	2	0.95	0.3	0	4	f	none
585	4656f23b-ed40-43d1-a314-94bbdedf5d29		4	3	14	2	10	2	0.95	0.3	0	4	f	none
586	4656f23b-ed40-43d1-a314-94bbdedf5d29		4	5	14	2	18	2	0.95	0.3	0	4	f	none
587	4656f23b-ed40-43d1-a314-94bbdedf5d29		5	4	18	2	14	2	0.95	0.3	0	4	f	none
588	4656f23b-ed40-43d1-a314-94bbdedf5d29		6	7	2	6	6	6	0.95	0.3	0	4	f	none
589	4656f23b-ed40-43d1-a314-94bbdedf5d29		7	6	6	6	2	6	0.95	0.3	0	4	f	none
590	4656f23b-ed40-43d1-a314-94bbdedf5d29		7	8	6	6	10	6	0.95	0.3	0	4	f	none
591	4656f23b-ed40-43d1-a314-94bbdedf5d29		8	7	10	6	6	6	0.95	0.3	0	4	f	none
592	4656f23b-ed40-43d1-a314-94bbdedf5d29		8	9	10	6	14	6	0.95	0.3	0	4	f	none
593	4656f23b-ed40-43d1-a314-94bbdedf5d29		9	8	14	6	10	6	0.95	0.3	0	4	f	none
594	4656f23b-ed40-43d1-a314-94bbdedf5d29		9	10	14	6	18	6	0.95	0.3	0	4	f	none
595	4656f23b-ed40-43d1-a314-94bbdedf5d29		10	9	18	6	14	6	0.95	0.3	0	4	f	none
596	4656f23b-ed40-43d1-a314-94bbdedf5d29		11	12	2	10	6	10	0.95	0.3	0	4	f	none
597	4656f23b-ed40-43d1-a314-94bbdedf5d29		12	11	6	10	2	10	0.95	0.3	0	4	f	none
598	ceed0bd3-7f76-46e4-b188-61010dcd100a		1	2	2	2	6	2	0.95	0.3	0	4	f	none
599	ceed0bd3-7f76-46e4-b188-61010dcd100a		2	1	6	2	2	2	0.95	0.3	0	4	f	none
600	ceed0bd3-7f76-46e4-b188-61010dcd100a		12	13	6	10	10	10	0.95	0.3	0	4	f	none
601	ceed0bd3-7f76-46e4-b188-61010dcd100a		13	12	10	10	6	10	0.95	0.3	0	4	f	none
602	ceed0bd3-7f76-46e4-b188-61010dcd100a		13	14	10	10	14	10	0.95	0.3	0	4	f	none
603	ceed0bd3-7f76-46e4-b188-61010dcd100a		14	13	14	10	10	10	0.95	0.3	0	4	f	none
604	ceed0bd3-7f76-46e4-b188-61010dcd100a		14	15	14	10	18	10	0.95	0.3	0	4	f	none
605	ceed0bd3-7f76-46e4-b188-61010dcd100a		15	14	18	10	14	10	0.95	0.3	0	4	f	none
606	ceed0bd3-7f76-46e4-b188-61010dcd100a		1	6	2	2	2	6	0.95	0.3	0	4	f	none
607	ceed0bd3-7f76-46e4-b188-61010dcd100a		6	1	2	6	2	2	0.95	0.3	0	4	f	none
608	ceed0bd3-7f76-46e4-b188-61010dcd100a		6	11	2	6	2	10	0.95	0.3	0	4	f	none
609	ceed0bd3-7f76-46e4-b188-61010dcd100a		11	6	2	10	2	6	0.95	0.3	0	4	f	none
610	ceed0bd3-7f76-46e4-b188-61010dcd100a		2	7	6	2	6	6	0.95	0.3	0	4	f	none
611	ceed0bd3-7f76-46e4-b188-61010dcd100a		7	2	6	6	6	2	0.95	0.3	0	4	f	none
612	ceed0bd3-7f76-46e4-b188-61010dcd100a		7	12	6	6	6	10	0.95	0.3	0	4	f	none
613	ceed0bd3-7f76-46e4-b188-61010dcd100a		12	7	6	10	6	6	0.95	0.3	0	4	f	none
614	ceed0bd3-7f76-46e4-b188-61010dcd100a		3	8	10	2	10	6	0.95	0.3	0	4	f	none
615	ceed0bd3-7f76-46e4-b188-61010dcd100a		8	3	10	6	10	2	0.95	0.3	0	4	f	none
616	ceed0bd3-7f76-46e4-b188-61010dcd100a		8	13	10	6	10	10	0.95	0.3	0	4	f	none
617	ceed0bd3-7f76-46e4-b188-61010dcd100a		13	8	10	10	10	6	0.95	0.3	0	4	f	none
618	ceed0bd3-7f76-46e4-b188-61010dcd100a		4	9	14	2	14	6	0.95	0.3	0	4	f	none
619	ceed0bd3-7f76-46e4-b188-61010dcd100a		9	4	14	6	14	2	0.95	0.3	0	4	f	none
620	ceed0bd3-7f76-46e4-b188-61010dcd100a		2	3	6	2	10	2	0.95	0.3	0	4	f	none
621	ceed0bd3-7f76-46e4-b188-61010dcd100a		3	2	10	2	6	2	0.95	0.3	0	4	f	none
622	ceed0bd3-7f76-46e4-b188-61010dcd100a		9	14	14	6	14	10	0.95	0.3	0	4	f	none
623	ceed0bd3-7f76-46e4-b188-61010dcd100a		14	9	14	10	14	6	0.95	0.3	0	4	f	none
624	ceed0bd3-7f76-46e4-b188-61010dcd100a		5	10	18	2	18	6	0.95	0.3	0	4	f	none
625	ceed0bd3-7f76-46e4-b188-61010dcd100a		10	5	18	6	18	2	0.95	0.3	0	4	f	none
626	ceed0bd3-7f76-46e4-b188-61010dcd100a		10	15	18	6	18	10	0.95	0.3	0	4	f	none
627	ceed0bd3-7f76-46e4-b188-61010dcd100a		15	10	18	10	18	6	0.95	0.3	0	4	f	none
628	ceed0bd3-7f76-46e4-b188-61010dcd100a		16	17	10	6	14	6	0.95	0.3	0	4	f	none
629	ceed0bd3-7f76-46e4-b188-61010dcd100a		17	16	14	6	10	6	0.95	0.3	0	4	f	none
630	ceed0bd3-7f76-46e4-b188-61010dcd100a		16	18	10	6	10	10	0.95	0.3	0	4	f	none
631	ceed0bd3-7f76-46e4-b188-61010dcd100a		18	16	10	10	10	6	0.95	0.3	0	4	f	none
632	ceed0bd3-7f76-46e4-b188-61010dcd100a		18	19	10	10	14	10	0.95	0.3	0	4	f	none
633	ceed0bd3-7f76-46e4-b188-61010dcd100a		19	18	14	10	10	10	0.95	0.3	0	4	f	none
634	ceed0bd3-7f76-46e4-b188-61010dcd100a		19	20	14	10	18	10	0.95	0.3	0	4	f	none
635	ceed0bd3-7f76-46e4-b188-61010dcd100a		20	19	18	10	14	10	0.95	0.3	0	4	f	none
636	ceed0bd3-7f76-46e4-b188-61010dcd100a		17	19	14	6	14	10	0.95	0.3	0	4	f	none
637	ceed0bd3-7f76-46e4-b188-61010dcd100a		19	17	14	10	14	6	0.95	0.3	0	4	f	none
638	ceed0bd3-7f76-46e4-b188-61010dcd100a		3	4	10	2	14	2	0.95	0.3	0	4	f	none
639	ceed0bd3-7f76-46e4-b188-61010dcd100a		4	3	14	2	10	2	0.95	0.3	0	4	f	none
640	ceed0bd3-7f76-46e4-b188-61010dcd100a		4	5	14	2	18	2	0.95	0.3	0	4	f	none
641	ceed0bd3-7f76-46e4-b188-61010dcd100a		5	4	18	2	14	2	0.95	0.3	0	4	f	none
642	ceed0bd3-7f76-46e4-b188-61010dcd100a		6	7	2	6	6	6	0.95	0.3	0	4	f	none
643	ceed0bd3-7f76-46e4-b188-61010dcd100a		7	6	6	6	2	6	0.95	0.3	0	4	f	none
644	ceed0bd3-7f76-46e4-b188-61010dcd100a		7	8	6	6	10	6	0.95	0.3	0	4	f	none
645	ceed0bd3-7f76-46e4-b188-61010dcd100a		8	7	10	6	6	6	0.95	0.3	0	4	f	none
646	ceed0bd3-7f76-46e4-b188-61010dcd100a		8	9	10	6	14	6	0.95	0.3	0	4	f	none
647	ceed0bd3-7f76-46e4-b188-61010dcd100a		9	8	14	6	10	6	0.95	0.3	0	4	f	none
648	ceed0bd3-7f76-46e4-b188-61010dcd100a		9	10	14	6	18	6	0.95	0.3	0	4	f	none
649	ceed0bd3-7f76-46e4-b188-61010dcd100a		10	9	18	6	14	6	0.95	0.3	0	4	f	none
650	ceed0bd3-7f76-46e4-b188-61010dcd100a		11	12	2	10	6	10	0.95	0.3	0	4	f	none
651	ceed0bd3-7f76-46e4-b188-61010dcd100a		12	11	6	10	2	10	0.95	0.3	0	4	f	none
652	98162503-c3c3-452f-a896-e85ded516cb9		1	2	2	2	6	2	0.95	0.3	0	4	f	none
653	98162503-c3c3-452f-a896-e85ded516cb9		2	1	6	2	2	2	0.95	0.3	0	4	f	none
654	98162503-c3c3-452f-a896-e85ded516cb9		12	13	6	10	10	10	0.95	0.3	0	4	f	none
655	98162503-c3c3-452f-a896-e85ded516cb9		13	12	10	10	6	10	0.95	0.3	0	4	f	none
656	98162503-c3c3-452f-a896-e85ded516cb9		13	14	10	10	14	10	0.95	0.3	0	4	f	none
657	98162503-c3c3-452f-a896-e85ded516cb9		14	13	14	10	10	10	0.95	0.3	0	4	f	none
658	98162503-c3c3-452f-a896-e85ded516cb9		14	15	14	10	18	10	0.95	0.3	0	4	f	none
659	98162503-c3c3-452f-a896-e85ded516cb9		15	14	18	10	14	10	0.95	0.3	0	4	f	none
660	98162503-c3c3-452f-a896-e85ded516cb9		1	6	2	2	2	6	0.95	0.3	0	4	f	none
661	98162503-c3c3-452f-a896-e85ded516cb9		6	1	2	6	2	2	0.95	0.3	0	4	f	none
662	98162503-c3c3-452f-a896-e85ded516cb9		6	11	2	6	2	10	0.95	0.3	0	4	f	none
663	98162503-c3c3-452f-a896-e85ded516cb9		11	6	2	10	2	6	0.95	0.3	0	4	f	none
664	98162503-c3c3-452f-a896-e85ded516cb9		2	7	6	2	6	6	0.95	0.3	0	4	f	none
665	98162503-c3c3-452f-a896-e85ded516cb9		7	2	6	6	6	2	0.95	0.3	0	4	f	none
666	98162503-c3c3-452f-a896-e85ded516cb9		7	12	6	6	6	10	0.95	0.3	0	4	f	none
667	98162503-c3c3-452f-a896-e85ded516cb9		12	7	6	10	6	6	0.95	0.3	0	4	f	none
668	98162503-c3c3-452f-a896-e85ded516cb9		3	8	10	2	10	6	0.95	0.3	0	4	f	none
669	98162503-c3c3-452f-a896-e85ded516cb9		8	3	10	6	10	2	0.95	0.3	0	4	f	none
670	98162503-c3c3-452f-a896-e85ded516cb9		8	13	10	6	10	10	0.95	0.3	0	4	f	none
671	98162503-c3c3-452f-a896-e85ded516cb9		13	8	10	10	10	6	0.95	0.3	0	4	f	none
672	98162503-c3c3-452f-a896-e85ded516cb9		4	9	14	2	14	6	0.95	0.3	0	4	f	none
673	98162503-c3c3-452f-a896-e85ded516cb9		9	4	14	6	14	2	0.95	0.3	0	4	f	none
674	98162503-c3c3-452f-a896-e85ded516cb9		2	3	6	2	10	2	0.95	0.3	0	4	f	none
675	98162503-c3c3-452f-a896-e85ded516cb9		3	2	10	2	6	2	0.95	0.3	0	4	f	none
676	98162503-c3c3-452f-a896-e85ded516cb9		9	14	14	6	14	10	0.95	0.3	0	4	f	none
677	98162503-c3c3-452f-a896-e85ded516cb9		14	9	14	10	14	6	0.95	0.3	0	4	f	none
678	98162503-c3c3-452f-a896-e85ded516cb9		5	10	18	2	18	6	0.95	0.3	0	4	f	none
679	98162503-c3c3-452f-a896-e85ded516cb9		10	5	18	6	18	2	0.95	0.3	0	4	f	none
680	98162503-c3c3-452f-a896-e85ded516cb9		10	15	18	6	18	10	0.95	0.3	0	4	f	none
681	98162503-c3c3-452f-a896-e85ded516cb9		15	10	18	10	18	6	0.95	0.3	0	4	f	none
682	98162503-c3c3-452f-a896-e85ded516cb9		16	17	10	6	14	6	0.95	0.3	0	4	f	none
683	98162503-c3c3-452f-a896-e85ded516cb9		17	16	14	6	10	6	0.95	0.3	0	4	f	none
684	98162503-c3c3-452f-a896-e85ded516cb9		16	18	10	6	10	10	0.95	0.3	0	4	f	none
685	98162503-c3c3-452f-a896-e85ded516cb9		18	16	10	10	10	6	0.95	0.3	0	4	f	none
686	98162503-c3c3-452f-a896-e85ded516cb9		18	19	10	10	14	10	0.95	0.3	0	4	f	none
687	98162503-c3c3-452f-a896-e85ded516cb9		19	18	14	10	10	10	0.95	0.3	0	4	f	none
688	98162503-c3c3-452f-a896-e85ded516cb9		19	20	14	10	18	10	0.95	0.3	0	4	f	none
689	98162503-c3c3-452f-a896-e85ded516cb9		20	19	18	10	14	10	0.95	0.3	0	4	f	none
690	98162503-c3c3-452f-a896-e85ded516cb9		17	19	14	6	14	10	0.95	0.3	0	4	f	none
691	98162503-c3c3-452f-a896-e85ded516cb9		19	17	14	10	14	6	0.95	0.3	0	4	f	none
692	98162503-c3c3-452f-a896-e85ded516cb9		3	4	10	2	14	2	0.95	0.3	0	4	f	none
693	98162503-c3c3-452f-a896-e85ded516cb9		4	3	14	2	10	2	0.95	0.3	0	4	f	none
694	98162503-c3c3-452f-a896-e85ded516cb9		4	5	14	2	18	2	0.95	0.3	0	4	f	none
695	98162503-c3c3-452f-a896-e85ded516cb9		5	4	18	2	14	2	0.95	0.3	0	4	f	none
696	98162503-c3c3-452f-a896-e85ded516cb9		6	7	2	6	6	6	0.95	0.3	0	4	f	none
697	98162503-c3c3-452f-a896-e85ded516cb9		7	6	6	6	2	6	0.95	0.3	0	4	f	none
698	98162503-c3c3-452f-a896-e85ded516cb9		7	8	6	6	10	6	0.95	0.3	0	4	f	none
699	98162503-c3c3-452f-a896-e85ded516cb9		8	7	10	6	6	6	0.95	0.3	0	4	f	none
700	98162503-c3c3-452f-a896-e85ded516cb9		8	9	10	6	14	6	0.95	0.3	0	4	f	none
701	98162503-c3c3-452f-a896-e85ded516cb9		9	8	14	6	10	6	0.95	0.3	0	4	f	none
702	98162503-c3c3-452f-a896-e85ded516cb9		9	10	14	6	18	6	0.95	0.3	0	4	f	none
703	98162503-c3c3-452f-a896-e85ded516cb9		10	9	18	6	14	6	0.95	0.3	0	4	f	none
704	98162503-c3c3-452f-a896-e85ded516cb9		11	12	2	10	6	10	0.95	0.3	0	4	f	none
705	98162503-c3c3-452f-a896-e85ded516cb9		12	11	6	10	2	10	0.95	0.3	0	4	f	none
706	b6fcdc48-990f-4dfd-a50e-2eabca664196		1	2	2	2	6	2	0.95	0.3	0	4	f	none
707	b6fcdc48-990f-4dfd-a50e-2eabca664196		2	1	6	2	2	2	0.95	0.3	0	4	f	none
708	b6fcdc48-990f-4dfd-a50e-2eabca664196		12	13	6	10	10	10	0.95	0.3	0	4	f	none
709	b6fcdc48-990f-4dfd-a50e-2eabca664196		13	12	10	10	6	10	0.95	0.3	0	4	f	none
710	b6fcdc48-990f-4dfd-a50e-2eabca664196		13	14	10	10	14	10	0.95	0.3	0	4	f	none
711	b6fcdc48-990f-4dfd-a50e-2eabca664196		14	13	14	10	10	10	0.95	0.3	0	4	f	none
712	b6fcdc48-990f-4dfd-a50e-2eabca664196		14	15	14	10	18	10	0.95	0.3	0	4	f	none
713	b6fcdc48-990f-4dfd-a50e-2eabca664196		15	14	18	10	14	10	0.95	0.3	0	4	f	none
714	b6fcdc48-990f-4dfd-a50e-2eabca664196		1	6	2	2	2	6	0.95	0.3	0	4	f	none
715	b6fcdc48-990f-4dfd-a50e-2eabca664196		6	1	2	6	2	2	0.95	0.3	0	4	f	none
716	b6fcdc48-990f-4dfd-a50e-2eabca664196		6	11	2	6	2	10	0.95	0.3	0	4	f	none
717	b6fcdc48-990f-4dfd-a50e-2eabca664196		11	6	2	10	2	6	0.95	0.3	0	4	f	none
718	b6fcdc48-990f-4dfd-a50e-2eabca664196		2	7	6	2	6	6	0.95	0.3	0	4	f	none
719	b6fcdc48-990f-4dfd-a50e-2eabca664196		7	2	6	6	6	2	0.95	0.3	0	4	f	none
720	b6fcdc48-990f-4dfd-a50e-2eabca664196		7	12	6	6	6	10	0.95	0.3	0	4	f	none
721	b6fcdc48-990f-4dfd-a50e-2eabca664196		12	7	6	10	6	6	0.95	0.3	0	4	f	none
722	b6fcdc48-990f-4dfd-a50e-2eabca664196		3	8	10	2	10	6	0.95	0.3	0	4	f	none
723	b6fcdc48-990f-4dfd-a50e-2eabca664196		8	3	10	6	10	2	0.95	0.3	0	4	f	none
724	b6fcdc48-990f-4dfd-a50e-2eabca664196		8	13	10	6	10	10	0.95	0.3	0	4	f	none
725	b6fcdc48-990f-4dfd-a50e-2eabca664196		13	8	10	10	10	6	0.95	0.3	0	4	f	none
726	b6fcdc48-990f-4dfd-a50e-2eabca664196		4	9	14	2	14	6	0.95	0.3	0	4	f	none
727	b6fcdc48-990f-4dfd-a50e-2eabca664196		9	4	14	6	14	2	0.95	0.3	0	4	f	none
728	b6fcdc48-990f-4dfd-a50e-2eabca664196		2	3	6	2	10	2	0.95	0.3	0	4	f	none
729	b6fcdc48-990f-4dfd-a50e-2eabca664196		3	2	10	2	6	2	0.95	0.3	0	4	f	none
730	b6fcdc48-990f-4dfd-a50e-2eabca664196		9	14	14	6	14	10	0.95	0.3	0	4	f	none
731	b6fcdc48-990f-4dfd-a50e-2eabca664196		14	9	14	10	14	6	0.95	0.3	0	4	f	none
732	b6fcdc48-990f-4dfd-a50e-2eabca664196		5	10	18	2	18	6	0.95	0.3	0	4	f	none
733	b6fcdc48-990f-4dfd-a50e-2eabca664196		10	5	18	6	18	2	0.95	0.3	0	4	f	none
734	b6fcdc48-990f-4dfd-a50e-2eabca664196		10	15	18	6	18	10	0.95	0.3	0	4	f	none
735	b6fcdc48-990f-4dfd-a50e-2eabca664196		15	10	18	10	18	6	0.95	0.3	0	4	f	none
736	b6fcdc48-990f-4dfd-a50e-2eabca664196		16	17	10	6	14	6	0.95	0.3	0	4	f	none
737	b6fcdc48-990f-4dfd-a50e-2eabca664196		17	16	14	6	10	6	0.95	0.3	0	4	f	none
738	b6fcdc48-990f-4dfd-a50e-2eabca664196		16	18	10	6	10	10	0.95	0.3	0	4	f	none
739	b6fcdc48-990f-4dfd-a50e-2eabca664196		18	16	10	10	10	6	0.95	0.3	0	4	f	none
740	b6fcdc48-990f-4dfd-a50e-2eabca664196		18	19	10	10	14	10	0.95	0.3	0	4	f	none
741	b6fcdc48-990f-4dfd-a50e-2eabca664196		19	18	14	10	10	10	0.95	0.3	0	4	f	none
742	b6fcdc48-990f-4dfd-a50e-2eabca664196		19	20	14	10	18	10	0.95	0.3	0	4	f	none
743	b6fcdc48-990f-4dfd-a50e-2eabca664196		20	19	18	10	14	10	0.95	0.3	0	4	f	none
744	b6fcdc48-990f-4dfd-a50e-2eabca664196		17	19	14	6	14	10	0.95	0.3	0	4	f	none
745	b6fcdc48-990f-4dfd-a50e-2eabca664196		19	17	14	10	14	6	0.95	0.3	0	4	f	none
746	b6fcdc48-990f-4dfd-a50e-2eabca664196		3	4	10	2	14	2	0.95	0.3	0	4	f	none
747	b6fcdc48-990f-4dfd-a50e-2eabca664196		4	3	14	2	10	2	0.95	0.3	0	4	f	none
748	b6fcdc48-990f-4dfd-a50e-2eabca664196		4	5	14	2	18	2	0.95	0.3	0	4	f	none
749	b6fcdc48-990f-4dfd-a50e-2eabca664196		5	4	18	2	14	2	0.95	0.3	0	4	f	none
750	b6fcdc48-990f-4dfd-a50e-2eabca664196		6	7	2	6	6	6	0.95	0.3	0	4	f	none
751	b6fcdc48-990f-4dfd-a50e-2eabca664196		7	6	6	6	2	6	0.95	0.3	0	4	f	none
752	b6fcdc48-990f-4dfd-a50e-2eabca664196		7	8	6	6	10	6	0.95	0.3	0	4	f	none
753	b6fcdc48-990f-4dfd-a50e-2eabca664196		8	7	10	6	6	6	0.95	0.3	0	4	f	none
754	b6fcdc48-990f-4dfd-a50e-2eabca664196		8	9	10	6	14	6	0.95	0.3	0	4	f	none
755	b6fcdc48-990f-4dfd-a50e-2eabca664196		9	8	14	6	10	6	0.95	0.3	0	4	f	none
756	b6fcdc48-990f-4dfd-a50e-2eabca664196		9	10	14	6	18	6	0.95	0.3	0	4	f	none
757	b6fcdc48-990f-4dfd-a50e-2eabca664196		10	9	18	6	14	6	0.95	0.3	0	4	f	none
758	b6fcdc48-990f-4dfd-a50e-2eabca664196		11	12	2	10	6	10	0.95	0.3	0	4	f	none
759	b6fcdc48-990f-4dfd-a50e-2eabca664196		12	11	6	10	2	10	0.95	0.3	0	4	f	none
760	61d76858-93a2-413d-9840-ea136908c9ab		1	2	2	2	6	2	0.95	0.3	0	4	f	none
761	61d76858-93a2-413d-9840-ea136908c9ab		2	1	6	2	2	2	0.95	0.3	0	4	f	none
762	61d76858-93a2-413d-9840-ea136908c9ab		12	13	6	10	10	10	0.95	0.3	0	4	f	none
763	61d76858-93a2-413d-9840-ea136908c9ab		13	12	10	10	6	10	0.95	0.3	0	4	f	none
764	61d76858-93a2-413d-9840-ea136908c9ab		13	14	10	10	14	10	0.95	0.3	0	4	f	none
765	61d76858-93a2-413d-9840-ea136908c9ab		14	13	14	10	10	10	0.95	0.3	0	4	f	none
766	61d76858-93a2-413d-9840-ea136908c9ab		14	15	14	10	18	10	0.95	0.3	0	4	f	none
767	61d76858-93a2-413d-9840-ea136908c9ab		15	14	18	10	14	10	0.95	0.3	0	4	f	none
768	61d76858-93a2-413d-9840-ea136908c9ab		1	6	2	2	2	6	0.95	0.3	0	4	f	none
769	61d76858-93a2-413d-9840-ea136908c9ab		6	1	2	6	2	2	0.95	0.3	0	4	f	none
770	61d76858-93a2-413d-9840-ea136908c9ab		6	11	2	6	2	10	0.95	0.3	0	4	f	none
771	61d76858-93a2-413d-9840-ea136908c9ab		11	6	2	10	2	6	0.95	0.3	0	4	f	none
772	61d76858-93a2-413d-9840-ea136908c9ab		2	7	6	2	6	6	0.95	0.3	0	4	f	none
773	61d76858-93a2-413d-9840-ea136908c9ab		7	2	6	6	6	2	0.95	0.3	0	4	f	none
774	61d76858-93a2-413d-9840-ea136908c9ab		7	12	6	6	6	10	0.95	0.3	0	4	f	none
775	61d76858-93a2-413d-9840-ea136908c9ab		12	7	6	10	6	6	0.95	0.3	0	4	f	none
776	61d76858-93a2-413d-9840-ea136908c9ab		3	8	10	2	10	6	0.95	0.3	0	4	f	none
777	61d76858-93a2-413d-9840-ea136908c9ab		8	3	10	6	10	2	0.95	0.3	0	4	f	none
778	61d76858-93a2-413d-9840-ea136908c9ab		8	13	10	6	10	10	0.95	0.3	0	4	f	none
779	61d76858-93a2-413d-9840-ea136908c9ab		13	8	10	10	10	6	0.95	0.3	0	4	f	none
780	61d76858-93a2-413d-9840-ea136908c9ab		4	9	14	2	14	6	0.95	0.3	0	4	f	none
781	61d76858-93a2-413d-9840-ea136908c9ab		9	4	14	6	14	2	0.95	0.3	0	4	f	none
782	61d76858-93a2-413d-9840-ea136908c9ab		2	3	6	2	10	2	0.95	0.3	0	4	f	none
783	61d76858-93a2-413d-9840-ea136908c9ab		3	2	10	2	6	2	0.95	0.3	0	4	f	none
784	61d76858-93a2-413d-9840-ea136908c9ab		9	14	14	6	14	10	0.95	0.3	0	4	f	none
785	61d76858-93a2-413d-9840-ea136908c9ab		14	9	14	10	14	6	0.95	0.3	0	4	f	none
786	61d76858-93a2-413d-9840-ea136908c9ab		5	10	18	2	18	6	0.95	0.3	0	4	f	none
787	61d76858-93a2-413d-9840-ea136908c9ab		10	5	18	6	18	2	0.95	0.3	0	4	f	none
788	61d76858-93a2-413d-9840-ea136908c9ab		10	15	18	6	18	10	0.95	0.3	0	4	f	none
789	61d76858-93a2-413d-9840-ea136908c9ab		15	10	18	10	18	6	0.95	0.3	0	4	f	none
790	61d76858-93a2-413d-9840-ea136908c9ab		16	17	10	6	14	6	0.95	0.3	0	4	f	none
791	61d76858-93a2-413d-9840-ea136908c9ab		17	16	14	6	10	6	0.95	0.3	0	4	f	none
792	61d76858-93a2-413d-9840-ea136908c9ab		16	18	10	6	10	10	0.95	0.3	0	4	f	none
793	61d76858-93a2-413d-9840-ea136908c9ab		18	16	10	10	10	6	0.95	0.3	0	4	f	none
794	61d76858-93a2-413d-9840-ea136908c9ab		18	19	10	10	14	10	0.95	0.3	0	4	f	none
795	61d76858-93a2-413d-9840-ea136908c9ab		19	18	14	10	10	10	0.95	0.3	0	4	f	none
796	61d76858-93a2-413d-9840-ea136908c9ab		19	20	14	10	18	10	0.95	0.3	0	4	f	none
797	61d76858-93a2-413d-9840-ea136908c9ab		20	19	18	10	14	10	0.95	0.3	0	4	f	none
798	61d76858-93a2-413d-9840-ea136908c9ab		17	19	14	6	14	10	0.95	0.3	0	4	f	none
799	61d76858-93a2-413d-9840-ea136908c9ab		19	17	14	10	14	6	0.95	0.3	0	4	f	none
800	61d76858-93a2-413d-9840-ea136908c9ab		3	4	10	2	14	2	0.95	0.3	0	4	f	none
801	61d76858-93a2-413d-9840-ea136908c9ab		4	3	14	2	10	2	0.95	0.3	0	4	f	none
802	61d76858-93a2-413d-9840-ea136908c9ab		4	5	14	2	18	2	0.95	0.3	0	4	f	none
803	61d76858-93a2-413d-9840-ea136908c9ab		5	4	18	2	14	2	0.95	0.3	0	4	f	none
804	61d76858-93a2-413d-9840-ea136908c9ab		6	7	2	6	6	6	0.95	0.3	0	4	f	none
805	61d76858-93a2-413d-9840-ea136908c9ab		7	6	6	6	2	6	0.95	0.3	0	4	f	none
806	61d76858-93a2-413d-9840-ea136908c9ab		7	8	6	6	10	6	0.95	0.3	0	4	f	none
807	61d76858-93a2-413d-9840-ea136908c9ab		8	7	10	6	6	6	0.95	0.3	0	4	f	none
808	61d76858-93a2-413d-9840-ea136908c9ab		8	9	10	6	14	6	0.95	0.3	0	4	f	none
809	61d76858-93a2-413d-9840-ea136908c9ab		9	8	14	6	10	6	0.95	0.3	0	4	f	none
810	61d76858-93a2-413d-9840-ea136908c9ab		9	10	14	6	18	6	0.95	0.3	0	4	f	none
811	61d76858-93a2-413d-9840-ea136908c9ab		10	9	18	6	14	6	0.95	0.3	0	4	f	none
812	61d76858-93a2-413d-9840-ea136908c9ab		11	12	2	10	6	10	0.95	0.3	0	4	f	none
813	61d76858-93a2-413d-9840-ea136908c9ab		12	11	6	10	2	10	0.95	0.3	0	4	f	none
814	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		1	2	2	2	6	2	0.95	0.3	0	4	f	none
815	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		2	1	6	2	2	2	0.95	0.3	0	4	f	none
816	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		12	13	6	10	10	10	0.95	0.3	0	4	f	none
817	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		13	12	10	10	6	10	0.95	0.3	0	4	f	none
818	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		13	14	10	10	14	10	0.95	0.3	0	4	f	none
819	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		14	13	14	10	10	10	0.95	0.3	0	4	f	none
820	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		14	15	14	10	18	10	0.95	0.3	0	4	f	none
821	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		15	14	18	10	14	10	0.95	0.3	0	4	f	none
822	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		1	6	2	2	2	6	0.95	0.3	0	4	f	none
823	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		6	1	2	6	2	2	0.95	0.3	0	4	f	none
824	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		6	11	2	6	2	10	0.95	0.3	0	4	f	none
825	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		11	6	2	10	2	6	0.95	0.3	0	4	f	none
826	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		2	7	6	2	6	6	0.95	0.3	0	4	f	none
827	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		7	2	6	6	6	2	0.95	0.3	0	4	f	none
828	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		7	12	6	6	6	10	0.95	0.3	0	4	f	none
829	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		12	7	6	10	6	6	0.95	0.3	0	4	f	none
830	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		3	8	10	2	10	6	0.95	0.3	0	4	f	none
831	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		8	3	10	6	10	2	0.95	0.3	0	4	f	none
832	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		8	13	10	6	10	10	0.95	0.3	0	4	f	none
833	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		13	8	10	10	10	6	0.95	0.3	0	4	f	none
834	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		4	9	14	2	14	6	0.95	0.3	0	4	f	none
835	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		9	4	14	6	14	2	0.95	0.3	0	4	f	none
836	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		2	3	6	2	10	2	0.95	0.3	0	4	f	none
837	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		3	2	10	2	6	2	0.95	0.3	0	4	f	none
838	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		9	14	14	6	14	10	0.95	0.3	0	4	f	none
839	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		14	9	14	10	14	6	0.95	0.3	0	4	f	none
840	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		5	10	18	2	18	6	0.95	0.3	0	4	f	none
841	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		10	5	18	6	18	2	0.95	0.3	0	4	f	none
842	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		10	15	18	6	18	10	0.95	0.3	0	4	f	none
843	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		15	10	18	10	18	6	0.95	0.3	0	4	f	none
844	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		16	17	10	6	14	6	0.95	0.3	0	4	f	none
845	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		17	16	14	6	10	6	0.95	0.3	0	4	f	none
846	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		16	18	10	6	10	10	0.95	0.3	0	4	f	none
847	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		18	16	10	10	10	6	0.95	0.3	0	4	f	none
848	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		18	19	10	10	14	10	0.95	0.3	0	4	f	none
849	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		19	18	14	10	10	10	0.95	0.3	0	4	f	none
850	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		19	20	14	10	18	10	0.95	0.3	0	4	f	none
851	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		20	19	18	10	14	10	0.95	0.3	0	4	f	none
852	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		17	19	14	6	14	10	0.95	0.3	0	4	f	none
853	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		19	17	14	10	14	6	0.95	0.3	0	4	f	none
854	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		3	4	10	2	14	2	0.95	0.3	0	4	f	none
855	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		4	3	14	2	10	2	0.95	0.3	0	4	f	none
856	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		4	5	14	2	18	2	0.95	0.3	0	4	f	none
857	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		5	4	18	2	14	2	0.95	0.3	0	4	f	none
858	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		6	7	2	6	6	6	0.95	0.3	0	4	f	none
859	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		7	6	6	6	2	6	0.95	0.3	0	4	f	none
860	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		7	8	6	6	10	6	0.95	0.3	0	4	f	none
861	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		8	7	10	6	6	6	0.95	0.3	0	4	f	none
862	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		8	9	10	6	14	6	0.95	0.3	0	4	f	none
863	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		9	8	14	6	10	6	0.95	0.3	0	4	f	none
864	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		9	10	14	6	18	6	0.95	0.3	0	4	f	none
865	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		10	9	18	6	14	6	0.95	0.3	0	4	f	none
866	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		11	12	2	10	6	10	0.95	0.3	0	4	f	none
867	f54ea27c-6e7d-4a6e-b45f-28e814b2e378		12	11	6	10	2	10	0.95	0.3	0	4	f	none
868	88173d83-9aa6-4df1-aaa8-c06b63569fc5		1	2	2	2	6	2	0.95	0.3	0	4	f	none
869	88173d83-9aa6-4df1-aaa8-c06b63569fc5		2	1	6	2	2	2	0.95	0.3	0	4	f	none
870	88173d83-9aa6-4df1-aaa8-c06b63569fc5		12	13	6	10	10	10	0.95	0.3	0	4	f	none
871	88173d83-9aa6-4df1-aaa8-c06b63569fc5		13	12	10	10	6	10	0.95	0.3	0	4	f	none
872	88173d83-9aa6-4df1-aaa8-c06b63569fc5		13	14	10	10	14	10	0.95	0.3	0	4	f	none
873	88173d83-9aa6-4df1-aaa8-c06b63569fc5		14	13	14	10	10	10	0.95	0.3	0	4	f	none
874	88173d83-9aa6-4df1-aaa8-c06b63569fc5		14	15	14	10	18	10	0.95	0.3	0	4	f	none
875	88173d83-9aa6-4df1-aaa8-c06b63569fc5		15	14	18	10	14	10	0.95	0.3	0	4	f	none
876	88173d83-9aa6-4df1-aaa8-c06b63569fc5		1	6	2	2	2	6	0.95	0.3	0	4	f	none
877	88173d83-9aa6-4df1-aaa8-c06b63569fc5		6	1	2	6	2	2	0.95	0.3	0	4	f	none
878	88173d83-9aa6-4df1-aaa8-c06b63569fc5		6	11	2	6	2	10	0.95	0.3	0	4	f	none
879	88173d83-9aa6-4df1-aaa8-c06b63569fc5		11	6	2	10	2	6	0.95	0.3	0	4	f	none
880	88173d83-9aa6-4df1-aaa8-c06b63569fc5		2	7	6	2	6	6	0.95	0.3	0	4	f	none
881	88173d83-9aa6-4df1-aaa8-c06b63569fc5		7	2	6	6	6	2	0.95	0.3	0	4	f	none
882	88173d83-9aa6-4df1-aaa8-c06b63569fc5		7	12	6	6	6	10	0.95	0.3	0	4	f	none
883	88173d83-9aa6-4df1-aaa8-c06b63569fc5		12	7	6	10	6	6	0.95	0.3	0	4	f	none
884	88173d83-9aa6-4df1-aaa8-c06b63569fc5		3	8	10	2	10	6	0.95	0.3	0	4	f	none
885	88173d83-9aa6-4df1-aaa8-c06b63569fc5		8	3	10	6	10	2	0.95	0.3	0	4	f	none
886	88173d83-9aa6-4df1-aaa8-c06b63569fc5		8	13	10	6	10	10	0.95	0.3	0	4	f	none
887	88173d83-9aa6-4df1-aaa8-c06b63569fc5		13	8	10	10	10	6	0.95	0.3	0	4	f	none
888	88173d83-9aa6-4df1-aaa8-c06b63569fc5		4	9	14	2	14	6	0.95	0.3	0	4	f	none
889	88173d83-9aa6-4df1-aaa8-c06b63569fc5		9	4	14	6	14	2	0.95	0.3	0	4	f	none
890	88173d83-9aa6-4df1-aaa8-c06b63569fc5		2	3	6	2	10	2	0.95	0.3	0	4	f	none
891	88173d83-9aa6-4df1-aaa8-c06b63569fc5		3	2	10	2	6	2	0.95	0.3	0	4	f	none
892	88173d83-9aa6-4df1-aaa8-c06b63569fc5		9	14	14	6	14	10	0.95	0.3	0	4	f	none
893	88173d83-9aa6-4df1-aaa8-c06b63569fc5		14	9	14	10	14	6	0.95	0.3	0	4	f	none
894	88173d83-9aa6-4df1-aaa8-c06b63569fc5		5	10	18	2	18	6	0.95	0.3	0	4	f	none
895	88173d83-9aa6-4df1-aaa8-c06b63569fc5		10	5	18	6	18	2	0.95	0.3	0	4	f	none
896	88173d83-9aa6-4df1-aaa8-c06b63569fc5		10	15	18	6	18	10	0.95	0.3	0	4	f	none
897	88173d83-9aa6-4df1-aaa8-c06b63569fc5		15	10	18	10	18	6	0.95	0.3	0	4	f	none
898	88173d83-9aa6-4df1-aaa8-c06b63569fc5		16	17	10	6	14	6	0.95	0.3	0	4	f	none
899	88173d83-9aa6-4df1-aaa8-c06b63569fc5		17	16	14	6	10	6	0.95	0.3	0	4	f	none
900	88173d83-9aa6-4df1-aaa8-c06b63569fc5		16	18	10	6	10	10	0.95	0.3	0	4	f	none
901	88173d83-9aa6-4df1-aaa8-c06b63569fc5		18	16	10	10	10	6	0.95	0.3	0	4	f	none
902	88173d83-9aa6-4df1-aaa8-c06b63569fc5		18	19	10	10	14	10	0.95	0.3	0	4	f	none
903	88173d83-9aa6-4df1-aaa8-c06b63569fc5		19	18	14	10	10	10	0.95	0.3	0	4	f	none
904	88173d83-9aa6-4df1-aaa8-c06b63569fc5		19	20	14	10	18	10	0.95	0.3	0	4	f	none
905	88173d83-9aa6-4df1-aaa8-c06b63569fc5		20	19	18	10	14	10	0.95	0.3	0	4	f	none
906	88173d83-9aa6-4df1-aaa8-c06b63569fc5		17	19	14	6	14	10	0.95	0.3	0	4	f	none
907	88173d83-9aa6-4df1-aaa8-c06b63569fc5		19	17	14	10	14	6	0.95	0.3	0	4	f	none
908	88173d83-9aa6-4df1-aaa8-c06b63569fc5		3	4	10	2	14	2	0.95	0.3	0	4	f	none
909	88173d83-9aa6-4df1-aaa8-c06b63569fc5		4	3	14	2	10	2	0.95	0.3	0	4	f	none
910	88173d83-9aa6-4df1-aaa8-c06b63569fc5		4	5	14	2	18	2	0.95	0.3	0	4	f	none
911	88173d83-9aa6-4df1-aaa8-c06b63569fc5		5	4	18	2	14	2	0.95	0.3	0	4	f	none
912	88173d83-9aa6-4df1-aaa8-c06b63569fc5		6	7	2	6	6	6	0.95	0.3	0	4	f	none
913	88173d83-9aa6-4df1-aaa8-c06b63569fc5		7	6	6	6	2	6	0.95	0.3	0	4	f	none
914	88173d83-9aa6-4df1-aaa8-c06b63569fc5		7	8	6	6	10	6	0.95	0.3	0	4	f	none
915	88173d83-9aa6-4df1-aaa8-c06b63569fc5		8	7	10	6	6	6	0.95	0.3	0	4	f	none
916	88173d83-9aa6-4df1-aaa8-c06b63569fc5		8	9	10	6	14	6	0.95	0.3	0	4	f	none
917	88173d83-9aa6-4df1-aaa8-c06b63569fc5		9	8	14	6	10	6	0.95	0.3	0	4	f	none
918	88173d83-9aa6-4df1-aaa8-c06b63569fc5		9	10	14	6	18	6	0.95	0.3	0	4	f	none
919	88173d83-9aa6-4df1-aaa8-c06b63569fc5		10	9	18	6	14	6	0.95	0.3	0	4	f	none
920	88173d83-9aa6-4df1-aaa8-c06b63569fc5		11	12	2	10	6	10	0.95	0.3	0	4	f	none
921	88173d83-9aa6-4df1-aaa8-c06b63569fc5		12	11	6	10	2	10	0.95	0.3	0	4	f	none
922	b7badbae-9aaf-4f4a-9ed0-87096255212c		1	2	2	2	6	2	0.95	0.3	0	4	f	none
923	b7badbae-9aaf-4f4a-9ed0-87096255212c		2	1	6	2	2	2	0.95	0.3	0	4	f	none
924	b7badbae-9aaf-4f4a-9ed0-87096255212c		12	13	6	10	10	10	0.95	0.3	0	4	f	none
925	b7badbae-9aaf-4f4a-9ed0-87096255212c		13	12	10	10	6	10	0.95	0.3	0	4	f	none
926	b7badbae-9aaf-4f4a-9ed0-87096255212c		13	14	10	10	14	10	0.95	0.3	0	4	f	none
927	b7badbae-9aaf-4f4a-9ed0-87096255212c		14	13	14	10	10	10	0.95	0.3	0	4	f	none
928	b7badbae-9aaf-4f4a-9ed0-87096255212c		14	15	14	10	18	10	0.95	0.3	0	4	f	none
929	b7badbae-9aaf-4f4a-9ed0-87096255212c		15	14	18	10	14	10	0.95	0.3	0	4	f	none
930	b7badbae-9aaf-4f4a-9ed0-87096255212c		1	6	2	2	2	6	0.95	0.3	0	4	f	none
931	b7badbae-9aaf-4f4a-9ed0-87096255212c		6	1	2	6	2	2	0.95	0.3	0	4	f	none
932	b7badbae-9aaf-4f4a-9ed0-87096255212c		6	11	2	6	2	10	0.95	0.3	0	4	f	none
933	b7badbae-9aaf-4f4a-9ed0-87096255212c		11	6	2	10	2	6	0.95	0.3	0	4	f	none
934	b7badbae-9aaf-4f4a-9ed0-87096255212c		2	7	6	2	6	6	0.95	0.3	0	4	f	none
935	b7badbae-9aaf-4f4a-9ed0-87096255212c		7	2	6	6	6	2	0.95	0.3	0	4	f	none
936	b7badbae-9aaf-4f4a-9ed0-87096255212c		7	12	6	6	6	10	0.95	0.3	0	4	f	none
937	b7badbae-9aaf-4f4a-9ed0-87096255212c		12	7	6	10	6	6	0.95	0.3	0	4	f	none
938	b7badbae-9aaf-4f4a-9ed0-87096255212c		3	8	10	2	10	6	0.95	0.3	0	4	f	none
939	b7badbae-9aaf-4f4a-9ed0-87096255212c		8	3	10	6	10	2	0.95	0.3	0	4	f	none
940	b7badbae-9aaf-4f4a-9ed0-87096255212c		8	13	10	6	10	10	0.95	0.3	0	4	f	none
941	b7badbae-9aaf-4f4a-9ed0-87096255212c		13	8	10	10	10	6	0.95	0.3	0	4	f	none
942	b7badbae-9aaf-4f4a-9ed0-87096255212c		4	9	14	2	14	6	0.95	0.3	0	4	f	none
943	b7badbae-9aaf-4f4a-9ed0-87096255212c		9	4	14	6	14	2	0.95	0.3	0	4	f	none
944	b7badbae-9aaf-4f4a-9ed0-87096255212c		2	3	6	2	10	2	0.95	0.3	0	4	f	none
945	b7badbae-9aaf-4f4a-9ed0-87096255212c		3	2	10	2	6	2	0.95	0.3	0	4	f	none
946	b7badbae-9aaf-4f4a-9ed0-87096255212c		9	14	14	6	14	10	0.95	0.3	0	4	f	none
947	b7badbae-9aaf-4f4a-9ed0-87096255212c		14	9	14	10	14	6	0.95	0.3	0	4	f	none
948	b7badbae-9aaf-4f4a-9ed0-87096255212c		5	10	18	2	18	6	0.95	0.3	0	4	f	none
949	b7badbae-9aaf-4f4a-9ed0-87096255212c		10	5	18	6	18	2	0.95	0.3	0	4	f	none
950	b7badbae-9aaf-4f4a-9ed0-87096255212c		10	15	18	6	18	10	0.95	0.3	0	4	f	none
951	b7badbae-9aaf-4f4a-9ed0-87096255212c		15	10	18	10	18	6	0.95	0.3	0	4	f	none
952	b7badbae-9aaf-4f4a-9ed0-87096255212c		16	17	10	6	14	6	0.95	0.3	0	4	f	none
953	b7badbae-9aaf-4f4a-9ed0-87096255212c		17	16	14	6	10	6	0.95	0.3	0	4	f	none
954	b7badbae-9aaf-4f4a-9ed0-87096255212c		16	18	10	6	10	10	0.95	0.3	0	4	f	none
955	b7badbae-9aaf-4f4a-9ed0-87096255212c		18	16	10	10	10	6	0.95	0.3	0	4	f	none
956	b7badbae-9aaf-4f4a-9ed0-87096255212c		18	19	10	10	14	10	0.95	0.3	0	4	f	none
957	b7badbae-9aaf-4f4a-9ed0-87096255212c		19	18	14	10	10	10	0.95	0.3	0	4	f	none
958	b7badbae-9aaf-4f4a-9ed0-87096255212c		19	20	14	10	18	10	0.95	0.3	0	4	f	none
959	b7badbae-9aaf-4f4a-9ed0-87096255212c		20	19	18	10	14	10	0.95	0.3	0	4	f	none
960	b7badbae-9aaf-4f4a-9ed0-87096255212c		17	19	14	6	14	10	0.95	0.3	0	4	f	none
961	b7badbae-9aaf-4f4a-9ed0-87096255212c		19	17	14	10	14	6	0.95	0.3	0	4	f	none
962	b7badbae-9aaf-4f4a-9ed0-87096255212c		3	4	10	2	14	2	0.95	0.3	0	4	f	none
963	b7badbae-9aaf-4f4a-9ed0-87096255212c		4	3	14	2	10	2	0.95	0.3	0	4	f	none
964	b7badbae-9aaf-4f4a-9ed0-87096255212c		4	5	14	2	18	2	0.95	0.3	0	4	f	none
965	b7badbae-9aaf-4f4a-9ed0-87096255212c		5	4	18	2	14	2	0.95	0.3	0	4	f	none
966	b7badbae-9aaf-4f4a-9ed0-87096255212c		6	7	2	6	6	6	0.95	0.3	0	4	f	none
967	b7badbae-9aaf-4f4a-9ed0-87096255212c		7	6	6	6	2	6	0.95	0.3	0	4	f	none
968	b7badbae-9aaf-4f4a-9ed0-87096255212c		7	8	6	6	10	6	0.95	0.3	0	4	f	none
969	b7badbae-9aaf-4f4a-9ed0-87096255212c		8	7	10	6	6	6	0.95	0.3	0	4	f	none
970	b7badbae-9aaf-4f4a-9ed0-87096255212c		8	9	10	6	14	6	0.95	0.3	0	4	f	none
971	b7badbae-9aaf-4f4a-9ed0-87096255212c		9	8	14	6	10	6	0.95	0.3	0	4	f	none
972	b7badbae-9aaf-4f4a-9ed0-87096255212c		9	10	14	6	18	6	0.95	0.3	0	4	f	none
973	b7badbae-9aaf-4f4a-9ed0-87096255212c		10	9	18	6	14	6	0.95	0.3	0	4	f	none
974	b7badbae-9aaf-4f4a-9ed0-87096255212c		11	12	2	10	6	10	0.95	0.3	0	4	f	none
975	b7badbae-9aaf-4f4a-9ed0-87096255212c		12	11	6	10	2	10	0.95	0.3	0	4	f	none
976	3772fe6a-6a43-4c30-a40e-125ddc5598c4		1	2	2	2	6	2	0.95	0.3	0	4	f	none
977	3772fe6a-6a43-4c30-a40e-125ddc5598c4		2	1	6	2	2	2	0.95	0.3	0	4	f	none
978	3772fe6a-6a43-4c30-a40e-125ddc5598c4		12	13	6	10	10	10	0.95	0.3	0	4	f	none
979	3772fe6a-6a43-4c30-a40e-125ddc5598c4		13	12	10	10	6	10	0.95	0.3	0	4	f	none
980	3772fe6a-6a43-4c30-a40e-125ddc5598c4		13	14	10	10	14	10	0.95	0.3	0	4	f	none
981	3772fe6a-6a43-4c30-a40e-125ddc5598c4		14	13	14	10	10	10	0.95	0.3	0	4	f	none
982	3772fe6a-6a43-4c30-a40e-125ddc5598c4		14	15	14	10	18	10	0.95	0.3	0	4	f	none
983	3772fe6a-6a43-4c30-a40e-125ddc5598c4		15	14	18	10	14	10	0.95	0.3	0	4	f	none
984	3772fe6a-6a43-4c30-a40e-125ddc5598c4		1	6	2	2	2	6	0.95	0.3	0	4	f	none
985	3772fe6a-6a43-4c30-a40e-125ddc5598c4		6	1	2	6	2	2	0.95	0.3	0	4	f	none
986	3772fe6a-6a43-4c30-a40e-125ddc5598c4		6	11	2	6	2	10	0.95	0.3	0	4	f	none
987	3772fe6a-6a43-4c30-a40e-125ddc5598c4		11	6	2	10	2	6	0.95	0.3	0	4	f	none
988	3772fe6a-6a43-4c30-a40e-125ddc5598c4		2	7	6	2	6	6	0.95	0.3	0	4	f	none
989	3772fe6a-6a43-4c30-a40e-125ddc5598c4		7	2	6	6	6	2	0.95	0.3	0	4	f	none
990	3772fe6a-6a43-4c30-a40e-125ddc5598c4		7	12	6	6	6	10	0.95	0.3	0	4	f	none
991	3772fe6a-6a43-4c30-a40e-125ddc5598c4		12	7	6	10	6	6	0.95	0.3	0	4	f	none
992	3772fe6a-6a43-4c30-a40e-125ddc5598c4		3	8	10	2	10	6	0.95	0.3	0	4	f	none
993	3772fe6a-6a43-4c30-a40e-125ddc5598c4		8	3	10	6	10	2	0.95	0.3	0	4	f	none
994	3772fe6a-6a43-4c30-a40e-125ddc5598c4		8	13	10	6	10	10	0.95	0.3	0	4	f	none
995	3772fe6a-6a43-4c30-a40e-125ddc5598c4		13	8	10	10	10	6	0.95	0.3	0	4	f	none
996	3772fe6a-6a43-4c30-a40e-125ddc5598c4		4	9	14	2	14	6	0.95	0.3	0	4	f	none
997	3772fe6a-6a43-4c30-a40e-125ddc5598c4		9	4	14	6	14	2	0.95	0.3	0	4	f	none
998	3772fe6a-6a43-4c30-a40e-125ddc5598c4		2	3	6	2	10	2	0.95	0.3	0	4	f	none
999	3772fe6a-6a43-4c30-a40e-125ddc5598c4		3	2	10	2	6	2	0.95	0.3	0	4	f	none
1000	3772fe6a-6a43-4c30-a40e-125ddc5598c4		9	14	14	6	14	10	0.95	0.3	0	4	f	none
1001	3772fe6a-6a43-4c30-a40e-125ddc5598c4		14	9	14	10	14	6	0.95	0.3	0	4	f	none
1002	3772fe6a-6a43-4c30-a40e-125ddc5598c4		5	10	18	2	18	6	0.95	0.3	0	4	f	none
1003	3772fe6a-6a43-4c30-a40e-125ddc5598c4		10	5	18	6	18	2	0.95	0.3	0	4	f	none
1004	3772fe6a-6a43-4c30-a40e-125ddc5598c4		10	15	18	6	18	10	0.95	0.3	0	4	f	none
1005	3772fe6a-6a43-4c30-a40e-125ddc5598c4		15	10	18	10	18	6	0.95	0.3	0	4	f	none
1006	3772fe6a-6a43-4c30-a40e-125ddc5598c4		16	17	10	6	14	6	0.95	0.3	0	4	f	none
1007	3772fe6a-6a43-4c30-a40e-125ddc5598c4		17	16	14	6	10	6	0.95	0.3	0	4	f	none
1008	3772fe6a-6a43-4c30-a40e-125ddc5598c4		16	18	10	6	10	10	0.95	0.3	0	4	f	none
1009	3772fe6a-6a43-4c30-a40e-125ddc5598c4		18	16	10	10	10	6	0.95	0.3	0	4	f	none
1010	3772fe6a-6a43-4c30-a40e-125ddc5598c4		18	19	10	10	14	10	0.95	0.3	0	4	f	none
1011	3772fe6a-6a43-4c30-a40e-125ddc5598c4		19	18	14	10	10	10	0.95	0.3	0	4	f	none
1012	3772fe6a-6a43-4c30-a40e-125ddc5598c4		19	20	14	10	18	10	0.95	0.3	0	4	f	none
1013	3772fe6a-6a43-4c30-a40e-125ddc5598c4		20	19	18	10	14	10	0.95	0.3	0	4	f	none
1014	3772fe6a-6a43-4c30-a40e-125ddc5598c4		17	19	14	6	14	10	0.95	0.3	0	4	f	none
1015	3772fe6a-6a43-4c30-a40e-125ddc5598c4		19	17	14	10	14	6	0.95	0.3	0	4	f	none
1016	3772fe6a-6a43-4c30-a40e-125ddc5598c4		3	4	10	2	14	2	0.95	0.3	0	4	f	none
1017	3772fe6a-6a43-4c30-a40e-125ddc5598c4		4	3	14	2	10	2	0.95	0.3	0	4	f	none
1018	3772fe6a-6a43-4c30-a40e-125ddc5598c4		4	5	14	2	18	2	0.95	0.3	0	4	f	none
1019	3772fe6a-6a43-4c30-a40e-125ddc5598c4		5	4	18	2	14	2	0.95	0.3	0	4	f	none
1020	3772fe6a-6a43-4c30-a40e-125ddc5598c4		6	7	2	6	6	6	0.95	0.3	0	4	f	none
1021	3772fe6a-6a43-4c30-a40e-125ddc5598c4		7	6	6	6	2	6	0.95	0.3	0	4	f	none
1022	3772fe6a-6a43-4c30-a40e-125ddc5598c4		7	8	6	6	10	6	0.95	0.3	0	4	f	none
1023	3772fe6a-6a43-4c30-a40e-125ddc5598c4		8	7	10	6	6	6	0.95	0.3	0	4	f	none
1024	3772fe6a-6a43-4c30-a40e-125ddc5598c4		8	9	10	6	14	6	0.95	0.3	0	4	f	none
1025	3772fe6a-6a43-4c30-a40e-125ddc5598c4		9	8	14	6	10	6	0.95	0.3	0	4	f	none
1026	3772fe6a-6a43-4c30-a40e-125ddc5598c4		9	10	14	6	18	6	0.95	0.3	0	4	f	none
1027	3772fe6a-6a43-4c30-a40e-125ddc5598c4		10	9	18	6	14	6	0.95	0.3	0	4	f	none
1028	3772fe6a-6a43-4c30-a40e-125ddc5598c4		11	12	2	10	6	10	0.95	0.3	0	4	f	none
1029	3772fe6a-6a43-4c30-a40e-125ddc5598c4		12	11	6	10	2	10	0.95	0.3	0	4	f	none
1030	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		1	2	2	2	6	2	0.95	0.3	0	4	f	none
1031	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		2	1	6	2	2	2	0.95	0.3	0	4	f	none
1032	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		12	13	6	10	10	10	0.95	0.3	0	4	f	none
1033	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		13	12	10	10	6	10	0.95	0.3	0	4	f	none
1034	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		13	14	10	10	14	10	0.95	0.3	0	4	f	none
1035	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		14	13	14	10	10	10	0.95	0.3	0	4	f	none
1036	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		14	15	14	10	18	10	0.95	0.3	0	4	f	none
1037	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		15	14	18	10	14	10	0.95	0.3	0	4	f	none
1038	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		1	6	2	2	2	6	0.95	0.3	0	4	f	none
1039	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		6	1	2	6	2	2	0.95	0.3	0	4	f	none
1040	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		6	11	2	6	2	10	0.95	0.3	0	4	f	none
1041	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		11	6	2	10	2	6	0.95	0.3	0	4	f	none
1042	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		2	7	6	2	6	6	0.95	0.3	0	4	f	none
1043	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		7	2	6	6	6	2	0.95	0.3	0	4	f	none
1044	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		7	12	6	6	6	10	0.95	0.3	0	4	f	none
1045	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		12	7	6	10	6	6	0.95	0.3	0	4	f	none
1046	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		3	8	10	2	10	6	0.95	0.3	0	4	f	none
1047	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		8	3	10	6	10	2	0.95	0.3	0	4	f	none
1048	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		8	13	10	6	10	10	0.95	0.3	0	4	f	none
1049	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		13	8	10	10	10	6	0.95	0.3	0	4	f	none
1050	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		4	9	14	2	14	6	0.95	0.3	0	4	f	none
1051	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		9	4	14	6	14	2	0.95	0.3	0	4	f	none
1052	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		2	3	6	2	10	2	0.95	0.3	0	4	f	none
1053	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		3	2	10	2	6	2	0.95	0.3	0	4	f	none
1054	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		9	14	14	6	14	10	0.95	0.3	0	4	f	none
1055	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		14	9	14	10	14	6	0.95	0.3	0	4	f	none
1056	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		5	10	18	2	18	6	0.95	0.3	0	4	f	none
1057	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		10	5	18	6	18	2	0.95	0.3	0	4	f	none
1058	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		10	15	18	6	18	10	0.95	0.3	0	4	f	none
1059	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		15	10	18	10	18	6	0.95	0.3	0	4	f	none
1060	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		16	17	10	6	14	6	0.95	0.3	0	4	f	none
1061	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		17	16	14	6	10	6	0.95	0.3	0	4	f	none
1062	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		16	18	10	6	10	10	0.95	0.3	0	4	f	none
1063	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		18	16	10	10	10	6	0.95	0.3	0	4	f	none
1064	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		18	19	10	10	14	10	0.95	0.3	0	4	f	none
1065	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		19	18	14	10	10	10	0.95	0.3	0	4	f	none
1066	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		19	20	14	10	18	10	0.95	0.3	0	4	f	none
1067	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		20	19	18	10	14	10	0.95	0.3	0	4	f	none
1068	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		17	19	14	6	14	10	0.95	0.3	0	4	f	none
1069	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		19	17	14	10	14	6	0.95	0.3	0	4	f	none
1070	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		3	4	10	2	14	2	0.95	0.3	0	4	f	none
1071	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		4	3	14	2	10	2	0.95	0.3	0	4	f	none
1072	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		4	5	14	2	18	2	0.95	0.3	0	4	f	none
1073	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		5	4	18	2	14	2	0.95	0.3	0	4	f	none
1074	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		6	7	2	6	6	6	0.95	0.3	0	4	f	none
1075	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		7	6	6	6	2	6	0.95	0.3	0	4	f	none
1076	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		7	8	6	6	10	6	0.95	0.3	0	4	f	none
1077	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		8	7	10	6	6	6	0.95	0.3	0	4	f	none
1078	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		8	9	10	6	14	6	0.95	0.3	0	4	f	none
1079	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		9	8	14	6	10	6	0.95	0.3	0	4	f	none
1080	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		9	10	14	6	18	6	0.95	0.3	0	4	f	none
1081	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		10	9	18	6	14	6	0.95	0.3	0	4	f	none
1082	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		11	12	2	10	6	10	0.95	0.3	0	4	f	none
1083	37b3a676-aa46-4650-aa23-9fa08b2c9e4f		12	11	6	10	2	10	0.95	0.3	0	4	f	none
1084	523fb5c2-e610-4f58-b471-646e295b8f15		1	6	2.037037037037037	11.981481481481481	5	11.981481481481481	0.95	0.3	0	2.962962962962963	f	none
1085	523fb5c2-e610-4f58-b471-646e295b8f15		6	1	5	11.981481481481481	2.037037037037037	11.981481481481481	0.95	0.3	0	2.962962962962963	f	none
1086	523fb5c2-e610-4f58-b471-646e295b8f15		3	4	1.9814814814814814	8	2	5.981481481481482	0.95	0.3	0	2.0186034640637853	f	none
1087	523fb5c2-e610-4f58-b471-646e295b8f15		4	3	2	5.981481481481482	1.9814814814814814	8	0.95	0.3	0	2.0186034640637853	f	none
1088	523fb5c2-e610-4f58-b471-646e295b8f15		4	5	2	5.981481481481482	1.962962962962963	3.9259259259259256	0.95	0.3	0	2.0558891954791227	f	none
1089	523fb5c2-e610-4f58-b471-646e295b8f15		5	4	1.962962962962963	3.9259259259259256	2	5.981481481481482	0.95	0.3	0	2.0558891954791227	f	none
1090	523fb5c2-e610-4f58-b471-646e295b8f15		5	10	1.962962962962963	3.9259259259259256	4.925925925925926	4.018518518518518	0.95	0.3	0	2.9644093691818743	f	none
1091	523fb5c2-e610-4f58-b471-646e295b8f15		10	5	4.925925925925926	4.018518518518518	1.962962962962963	3.9259259259259256	0.95	0.3	0	2.9644093691818743	f	none
1092	523fb5c2-e610-4f58-b471-646e295b8f15		10	9	4.925925925925926	4.018518518518518	4.981481481481482	6.037037037037037	0.95	0.3	0	2.0192828997828123	f	none
1093	523fb5c2-e610-4f58-b471-646e295b8f15		9	10	4.981481481481482	6.037037037037037	4.925925925925926	4.018518518518518	0.95	0.3	0	2.0192828997828123	f	none
1094	523fb5c2-e610-4f58-b471-646e295b8f15		9	14	4.981481481481482	6.037037037037037	7.981481481481482	6.037037037037037	0.95	0.3	0	3	f	none
1095	523fb5c2-e610-4f58-b471-646e295b8f15		14	9	7.981481481481482	6.037037037037037	4.981481481481482	6.037037037037037	0.95	0.3	0	3	f	none
1096	523fb5c2-e610-4f58-b471-646e295b8f15		14	15	7.981481481481482	6.037037037037037	8	4	0.95	0.3	0	2.0371212103821295	f	none
1097	523fb5c2-e610-4f58-b471-646e295b8f15		15	14	8	4	7.981481481481482	6.037037037037037	0.95	0.3	0	2.0371212103821295	f	none
1098	523fb5c2-e610-4f58-b471-646e295b8f15		15	10	8	4	4.925925925925926	4.018518518518518	0.95	0.3	0	3.0741298522382716	f	none
1099	523fb5c2-e610-4f58-b471-646e295b8f15		10	15	4.925925925925926	4.018518518518518	8	4	0.95	0.3	0	3.0741298522382716	f	none
1100	523fb5c2-e610-4f58-b471-646e295b8f15		8	13	4.981481481481482	8	7.907407407407407	8.055555555555555	0.95	0.3	0	2.9264533045580228	f	none
1101	523fb5c2-e610-4f58-b471-646e295b8f15		13	8	7.907407407407407	8.055555555555555	4.981481481481482	8	0.95	0.3	0	2.9264533045580228	f	none
1102	523fb5c2-e610-4f58-b471-646e295b8f15		13	14	7.907407407407407	8.055555555555555	7.981481481481482	6.037037037037037	0.95	0.3	0	2.0198772185586242	f	none
1103	523fb5c2-e610-4f58-b471-646e295b8f15		14	13	7.981481481481482	6.037037037037037	7.907407407407407	8.055555555555555	0.95	0.3	0	2.0198772185586242	f	none
1104	523fb5c2-e610-4f58-b471-646e295b8f15		14	8	7.981481481481482	6.037037037037037	4.981481481481482	8	0.95	0.3	0	3.585139271208907	f	none
1105	523fb5c2-e610-4f58-b471-646e295b8f15		8	14	4.981481481481482	8	7.981481481481482	6.037037037037037	0.95	0.3	0	3.585139271208907	f	none
1106	523fb5c2-e610-4f58-b471-646e295b8f15		6	7	5	11.981481481481481	4.981481481481482	10	0.95	0.3	0	1.9815680147252492	f	none
1107	523fb5c2-e610-4f58-b471-646e295b8f15		7	6	4.981481481481482	10	5	11.981481481481481	0.95	0.3	0	1.9815680147252492	f	none
1108	523fb5c2-e610-4f58-b471-646e295b8f15		12	13	7.981481481481482	10.055555555555555	7.907407407407407	8.055555555555555	0.95	0.3	0	2.0013712720157475	f	none
1109	523fb5c2-e610-4f58-b471-646e295b8f15		13	12	7.907407407407407	8.055555555555555	7.981481481481482	10.055555555555555	0.95	0.3	0	2.0013712720157475	f	none
1110	523fb5c2-e610-4f58-b471-646e295b8f15		12	7	7.981481481481482	10.055555555555555	4.981481481481482	10	0.95	0.3	0	3.0005143591979504	f	none
1111	523fb5c2-e610-4f58-b471-646e295b8f15		7	12	4.981481481481482	10	7.981481481481482	10.055555555555555	0.95	0.3	0	3.0005143591979504	f	none
1112	523fb5c2-e610-4f58-b471-646e295b8f15		8	12	4.981481481481482	8	7.981481481481482	10.055555555555555	0.95	0.3	0	3.6366617442340314	f	none
1113	523fb5c2-e610-4f58-b471-646e295b8f15		12	8	7.981481481481482	10.055555555555555	4.981481481481482	8	0.95	0.3	0	3.6366617442340314	f	none
1114	523fb5c2-e610-4f58-b471-646e295b8f15		12	11	7.981481481481482	10.055555555555555	8	12	0.95	0.3	0	1.944532625866428	f	none
1115	523fb5c2-e610-4f58-b471-646e295b8f15		11	12	8	12	7.981481481481482	10.055555555555555	0.95	0.3	0	1.944532625866428	f	none
1116	523fb5c2-e610-4f58-b471-646e295b8f15		12	19	7.981481481481482	10.055555555555555	10.944444444444445	9.88888888888889	0.95	0.3	0	2.967646760931637	f	none
1117	523fb5c2-e610-4f58-b471-646e295b8f15		19	12	10.944444444444445	9.88888888888889	7.981481481481482	10.055555555555555	0.95	0.3	0	2.967646760931637	f	none
1118	523fb5c2-e610-4f58-b471-646e295b8f15		19	18	10.944444444444445	9.88888888888889	11.037037037037036	8	0.95	0.3	0	1.891156953499873	f	none
1119	523fb5c2-e610-4f58-b471-646e295b8f15		18	19	11.037037037037036	8	10.944444444444445	9.88888888888889	0.95	0.3	0	1.891156953499873	f	none
1120	523fb5c2-e610-4f58-b471-646e295b8f15		18	13	11.037037037037036	8	7.907407407407407	8.055555555555555	0.95	0.3	0	3.1301226874371513	f	none
1121	523fb5c2-e610-4f58-b471-646e295b8f15		13	18	7.907407407407407	8.055555555555555	11.037037037037036	8	0.95	0.3	0	3.1301226874371513	f	none
1122	523fb5c2-e610-4f58-b471-646e295b8f15		14	17	7.981481481481482	6.037037037037037	11.037037037037036	6	0.95	0.3	0	3.0557800142024125	f	none
1123	523fb5c2-e610-4f58-b471-646e295b8f15		17	14	11.037037037037036	6	7.981481481481482	6.037037037037037	0.95	0.3	0	3.0557800142024125	f	none
1124	523fb5c2-e610-4f58-b471-646e295b8f15		17	18	11.037037037037036	6	11.037037037037036	8	0.95	0.3	0	2	f	none
1125	523fb5c2-e610-4f58-b471-646e295b8f15		18	17	11.037037037037036	8	11.037037037037036	6	0.95	0.3	0	2	f	none
1126	523fb5c2-e610-4f58-b471-646e295b8f15		17	16	11.037037037037036	6	10.981481481481481	4	0.95	0.3	0	2.000771456152123	f	none
1127	523fb5c2-e610-4f58-b471-646e295b8f15		16	17	10.981481481481481	4	11.037037037037036	6	0.95	0.3	0	2.000771456152123	f	none
1128	523fb5c2-e610-4f58-b471-646e295b8f15		7	2	4.981481481481482	10	1.9814814814814814	9.981481481481481	0.95	0.3	0	3.0000571553768975	f	none
1129	523fb5c2-e610-4f58-b471-646e295b8f15		2	7	1.9814814814814814	9.981481481481481	4.981481481481482	10	0.95	0.3	0	3.0000571553768975	f	none
1130	523fb5c2-e610-4f58-b471-646e295b8f15		16	15	10.981481481481481	4	8	4	0.95	0.3	0	2.981481481481481	f	none
1131	523fb5c2-e610-4f58-b471-646e295b8f15		15	16	8	4	10.981481481481481	4	0.95	0.3	0	2.981481481481481	f	none
1132	523fb5c2-e610-4f58-b471-646e295b8f15		17	23	11.037037037037036	6	13.851851851851851	7.2407407407407405	0.95	0.3	0	3.076137192557387	f	none
1133	523fb5c2-e610-4f58-b471-646e295b8f15		23	17	13.851851851851851	7.2407407407407405	11.037037037037036	6	0.95	0.3	0	3.076137192557387	f	none
1134	523fb5c2-e610-4f58-b471-646e295b8f15		18	23	11.037037037037036	8	13.851851851851851	7.2407407407407405	0.95	0.3	0	2.9154171338715633	f	none
1135	523fb5c2-e610-4f58-b471-646e295b8f15		23	18	13.851851851851851	7.2407407407407405	11.037037037037036	8	0.95	0.3	0	2.9154171338715633	f	none
1136	523fb5c2-e610-4f58-b471-646e295b8f15		19	22	10.944444444444445	9.88888888888889	13.962962962962964	10.074074074074074	0.95	0.3	0	3.02419371063616	f	none
1137	523fb5c2-e610-4f58-b471-646e295b8f15		22	19	13.962962962962964	10.074074074074074	10.944444444444445	9.88888888888889	0.95	0.3	0	3.02419371063616	f	none
1138	523fb5c2-e610-4f58-b471-646e295b8f15		23	24	13.851851851851851	7.2407407407407405	14.648148148148149	5.111111111111111	0.95	0.3	0	2.2736336888099706	f	none
1139	523fb5c2-e610-4f58-b471-646e295b8f15		24	23	14.648148148148149	5.111111111111111	13.851851851851851	7.2407407407407405	0.95	0.3	0	2.2736336888099706	f	none
1140	523fb5c2-e610-4f58-b471-646e295b8f15		24	16	14.648148148148149	5.111111111111111	10.981481481481481	4	0.95	0.3	0	3.8313199221259273	f	none
1141	523fb5c2-e610-4f58-b471-646e295b8f15		16	24	10.981481481481481	4	14.648148148148149	5.111111111111111	0.95	0.3	0	3.8313199221259273	f	none
1142	523fb5c2-e610-4f58-b471-646e295b8f15		24	25	14.648148148148149	5.111111111111111	17.09259259259259	3.9074074074074066	0.95	0.3	0	2.7247405836676113	f	none
1143	523fb5c2-e610-4f58-b471-646e295b8f15		25	24	17.09259259259259	3.9074074074074066	14.648148148148149	5.111111111111111	0.95	0.3	0	2.7247405836676113	f	none
1144	523fb5c2-e610-4f58-b471-646e295b8f15		25	16	17.09259259259259	3.9074074074074066	10.981481481481481	4	0.95	0.3	0	6.1118125298923145	f	none
1145	523fb5c2-e610-4f58-b471-646e295b8f15		16	25	10.981481481481481	4	17.09259259259259	3.9074074074074066	0.95	0.3	0	6.1118125298923145	f	none
1146	523fb5c2-e610-4f58-b471-646e295b8f15		25	26	17.09259259259259	3.9074074074074066	17.11111111111111	7.462962962962963	0.95	0.3	0	3.5556037805371536	f	none
1147	523fb5c2-e610-4f58-b471-646e295b8f15		26	25	17.11111111111111	7.462962962962963	17.09259259259259	3.9074074074074066	0.95	0.3	0	3.5556037805371536	f	none
1148	523fb5c2-e610-4f58-b471-646e295b8f15		26	24	17.11111111111111	7.462962962962963	14.648148148148149	5.111111111111111	0.95	0.3	0	3.405494632206352	f	none
1149	523fb5c2-e610-4f58-b471-646e295b8f15		24	26	14.648148148148149	5.111111111111111	17.11111111111111	7.462962962962963	0.95	0.3	0	3.405494632206352	f	none
1150	523fb5c2-e610-4f58-b471-646e295b8f15		1	2	2.037037037037037	11.981481481481481	1.9814814814814814	9.981481481481481	0.95	0.3	0	2.000771456152123	f	none
1151	523fb5c2-e610-4f58-b471-646e295b8f15		2	1	1.9814814814814814	9.981481481481481	2.037037037037037	11.981481481481481	0.95	0.3	0	2.000771456152123	f	none
1152	523fb5c2-e610-4f58-b471-646e295b8f15		23	27	13.851851851851851	7.2407407407407405	16.574074074074073	10.055555555555555	0.95	0.3	0	3.915823830161598	f	none
1153	523fb5c2-e610-4f58-b471-646e295b8f15		27	23	16.574074074074073	10.055555555555555	13.851851851851851	7.2407407407407405	0.95	0.3	0	3.915823830161598	f	none
1154	523fb5c2-e610-4f58-b471-646e295b8f15		27	26	16.574074074074073	10.055555555555555	17.11111111111111	7.462962962962963	0.95	0.3	0	2.6476300969575606	f	none
1155	523fb5c2-e610-4f58-b471-646e295b8f15		26	27	17.11111111111111	7.462962962962963	16.574074074074073	10.055555555555555	0.95	0.3	0	2.6476300969575606	f	none
1156	523fb5c2-e610-4f58-b471-646e295b8f15		22	27	13.962962962962964	10.074074074074074	16.574074074074073	10.055555555555555	0.95	0.3	0	2.6111767787907447	f	none
1157	523fb5c2-e610-4f58-b471-646e295b8f15		27	22	16.574074074074073	10.055555555555555	13.962962962962964	10.074074074074074	0.95	0.3	0	2.6111767787907447	f	none
1158	523fb5c2-e610-4f58-b471-646e295b8f15		27	21	16.574074074074073	10.055555555555555	14.962962962962964	12	0.95	0.3	0	2.52518181719189	f	none
1159	523fb5c2-e610-4f58-b471-646e295b8f15		21	27	14.962962962962964	12	16.574074074074073	10.055555555555555	0.95	0.3	0	2.52518181719189	f	none
1160	523fb5c2-e610-4f58-b471-646e295b8f15		21	22	14.962962962962964	12	13.962962962962964	10.074074074074074	0.95	0.3	0	2.170066974117074	f	none
1161	523fb5c2-e610-4f58-b471-646e295b8f15		22	21	13.962962962962964	10.074074074074074	14.962962962962964	12	0.95	0.3	0	2.170066974117074	f	none
1162	523fb5c2-e610-4f58-b471-646e295b8f15		20	19	10.925925925925926	11.962962962962964	10.944444444444445	9.88888888888889	0.95	0.3	0	2.0741567443841724	f	none
1163	523fb5c2-e610-4f58-b471-646e295b8f15		19	20	10.944444444444445	9.88888888888889	10.925925925925926	11.962962962962964	0.95	0.3	0	2.0741567443841724	f	none
1164	523fb5c2-e610-4f58-b471-646e295b8f15		20	21	10.925925925925926	11.962962962962964	14.962962962962964	12	0.95	0.3	0	4.037206928127572	f	none
1165	523fb5c2-e610-4f58-b471-646e295b8f15		21	20	14.962962962962964	12	10.925925925925926	11.962962962962964	0.95	0.3	0	4.037206928127572	f	none
1166	523fb5c2-e610-4f58-b471-646e295b8f15		22	23	13.962962962962964	10.074074074074074	13.851851851851851	7.2407407407407405	0.95	0.3	0	2.8355111455944106	f	none
1167	523fb5c2-e610-4f58-b471-646e295b8f15		23	22	13.851851851851851	7.2407407407407405	13.962962962962964	10.074074074074074	0.95	0.3	0	2.8355111455944106	f	none
1168	523fb5c2-e610-4f58-b471-646e295b8f15		2	3	1.9814814814814814	9.981481481481481	1.9814814814814814	8	0.95	0.3	0	1.981481481481481	f	none
1169	523fb5c2-e610-4f58-b471-646e295b8f15		3	2	1.9814814814814814	8	1.9814814814814814	9.981481481481481	0.95	0.3	0	1.981481481481481	f	none
1170	523fb5c2-e610-4f58-b471-646e295b8f15		3	8	1.9814814814814814	8	4.981481481481482	8	0.95	0.3	0	3.0000000000000004	f	none
1171	523fb5c2-e610-4f58-b471-646e295b8f15		8	3	4.981481481481482	8	1.9814814814814814	8	0.95	0.3	0	3.0000000000000004	f	none
1172	523fb5c2-e610-4f58-b471-646e295b8f15		8	7	4.981481481481482	8	4.981481481481482	10	0.95	0.3	0	2	f	none
1173	523fb5c2-e610-4f58-b471-646e295b8f15		7	8	4.981481481481482	10	4.981481481481482	8	0.95	0.3	0	2	f	none
1174	523fb5c2-e610-4f58-b471-646e295b8f15		8	9	4.981481481481482	8	4.981481481481482	6.037037037037037	0.95	0.3	0	1.9629629629629628	f	none
1175	523fb5c2-e610-4f58-b471-646e295b8f15		9	8	4.981481481481482	6.037037037037037	4.981481481481482	8	0.95	0.3	0	1.9629629629629628	f	none
1176	523fb5c2-e610-4f58-b471-646e295b8f15		9	4	4.981481481481482	6.037037037037037	2	5.981481481481482	0.95	0.3	0	2.9819990349042866	f	none
1177	523fb5c2-e610-4f58-b471-646e295b8f15		4	9	2	5.981481481481482	4.981481481481482	6.037037037037037	0.95	0.3	0	2.9819990349042866	f	none
1178	93e3ba66-0f9a-4267-95a1-71872f181779		13	14	2.074074074074075	18.085185185185185	9.953703703703704	18.085185185185185	0.95	0.3	0	7.87962962962963	f	none
1179	93e3ba66-0f9a-4267-95a1-71872f181779		14	13	9.953703703703704	18.085185185185185	2.074074074074075	18.085185185185185	0.95	0.3	0	7.87962962962963	f	none
1180	93e3ba66-0f9a-4267-95a1-71872f181779		8	7	9.996296296296297	9.822222222222223	1.9462962962962969	9.907407407407408	0.95	0.3	0	8.050450702648583	f	none
1181	93e3ba66-0f9a-4267-95a1-71872f181779		7	8	1.9462962962962969	9.907407407407408	9.996296296296297	9.822222222222223	0.95	0.3	0	8.050450702648583	f	none
1182	93e3ba66-0f9a-4267-95a1-71872f181779		6	1	2.15925925925926	6.031481481481482	1.9462962962962969	1.942592592592593	0.95	0.3	0	4.094431043414088	f	none
1183	93e3ba66-0f9a-4267-95a1-71872f181779		1	6	1.9462962962962969	1.942592592592593	2.15925925925926	6.031481481481482	0.95	0.3	0	4.094431043414088	f	none
1184	93e3ba66-0f9a-4267-95a1-71872f181779		5	2	10.081481481481482	6.116666666666667	9.953703703703704	1.9851851851851876	0.95	0.3	0	4.133456954211357	f	none
1185	93e3ba66-0f9a-4267-95a1-71872f181779		2	5	9.953703703703704	1.9851851851851876	10.081481481481482	6.116666666666667	0.95	0.3	0	4.133456954211357	f	none
1186	93e3ba66-0f9a-4267-95a1-71872f181779		1	2	1.9462962962962969	1.942592592592593	9.953703703703704	1.9851851851851876	0.95	0.3	0	8.007520684777953	f	none
1187	93e3ba66-0f9a-4267-95a1-71872f181779		2	1	9.953703703703704	1.9851851851851876	1.9462962962962969	1.942592592592593	0.95	0.3	0	8.007520684777953	f	none
1188	93e3ba66-0f9a-4267-95a1-71872f181779		2	3	9.953703703703704	1.9851851851851876	18.003703703703703	1.9851851851851876	0.95	0.3	0	8.049999999999999	f	none
1189	93e3ba66-0f9a-4267-95a1-71872f181779		3	2	18.003703703703703	1.9851851851851876	9.953703703703704	1.9851851851851876	0.95	0.3	0	8.049999999999999	f	none
1190	93e3ba66-0f9a-4267-95a1-71872f181779		3	4	18.003703703703703	1.9851851851851876	17.918518518518518	6.031481481481482	0.95	0.3	0	4.047192883122343	f	none
1191	93e3ba66-0f9a-4267-95a1-71872f181779		4	3	17.918518518518518	6.031481481481482	18.003703703703703	1.9851851851851876	0.95	0.3	0	4.047192883122343	f	none
1192	93e3ba66-0f9a-4267-95a1-71872f181779		4	5	17.918518518518518	6.031481481481482	10.081481481481482	6.116666666666667	0.95	0.3	0	7.837499986326333	f	none
1193	93e3ba66-0f9a-4267-95a1-71872f181779		5	4	10.081481481481482	6.116666666666667	17.918518518518518	6.031481481481482	0.95	0.3	0	7.837499986326333	f	none
1194	93e3ba66-0f9a-4267-95a1-71872f181779		4	9	17.918518518518518	6.031481481481482	18.003703703703703	9.992592592592594	0.95	0.3	0	3.9620269749640706	f	none
1195	93e3ba66-0f9a-4267-95a1-71872f181779		9	4	18.003703703703703	9.992592592592594	17.918518518518518	6.031481481481482	0.95	0.3	0	3.9620269749640706	f	none
1196	93e3ba66-0f9a-4267-95a1-71872f181779		9	8	18.003703703703703	9.992592592592594	9.996296296296297	9.822222222222223	0.95	0.3	0	8.009219653081262	f	none
1197	93e3ba66-0f9a-4267-95a1-71872f181779		8	9	9.996296296296297	9.822222222222223	18.003703703703703	9.992592592592594	0.95	0.3	0	8.009219653081262	f	none
1198	93e3ba66-0f9a-4267-95a1-71872f181779		10	9	17.961111111111112	13.911111111111111	18.003703703703703	9.992592592592594	0.95	0.3	0	3.9187499931631664	f	none
1199	93e3ba66-0f9a-4267-95a1-71872f181779		9	10	18.003703703703703	9.992592592592594	17.961111111111112	13.911111111111111	0.95	0.3	0	3.9187499931631664	f	none
1200	93e3ba66-0f9a-4267-95a1-71872f181779		11	12	9.911111111111111	13.996296296296297	2.2018518518518526	14.081481481481482	0.95	0.3	0	7.709729881276623	f	none
1201	93e3ba66-0f9a-4267-95a1-71872f181779		12	11	2.2018518518518526	14.081481481481482	9.911111111111111	13.996296296296297	0.95	0.3	0	7.709729881276623	f	none
1202	93e3ba66-0f9a-4267-95a1-71872f181779		11	10	9.911111111111111	13.996296296296297	17.961111111111112	13.911111111111111	0.95	0.3	0	8.050450702648583	f	none
1203	93e3ba66-0f9a-4267-95a1-71872f181779		10	11	17.961111111111112	13.911111111111111	9.911111111111111	13.996296296296297	0.95	0.3	0	8.050450702648583	f	none
1204	93e3ba66-0f9a-4267-95a1-71872f181779		10	15	17.961111111111112	13.911111111111111	17.833333333333332	17.914814814814815	0.95	0.3	0	4.005742191847171	f	none
1205	93e3ba66-0f9a-4267-95a1-71872f181779		15	10	17.833333333333332	17.914814814814815	17.961111111111112	13.911111111111111	0.95	0.3	0	4.005742191847171	f	none
1206	93e3ba66-0f9a-4267-95a1-71872f181779		14	15	9.953703703703704	18.085185185185185	17.833333333333332	17.914814814814815	0.95	0.3	0	7.8814712562590294	f	none
1207	93e3ba66-0f9a-4267-95a1-71872f181779		15	14	17.833333333333332	17.914814814814815	9.953703703703704	18.085185185185185	0.95	0.3	0	7.8814712562590294	f	none
1208	93e3ba66-0f9a-4267-95a1-71872f181779		15	16	17.833333333333332	17.914814814814815	24.05185185185185	15.912962962962963	0.95	0.3	0	6.532792925075801	f	none
1209	93e3ba66-0f9a-4267-95a1-71872f181779		16	15	24.05185185185185	15.912962962962963	17.833333333333332	17.914814814814815	0.95	0.3	0	6.532792925075801	f	none
1210	93e3ba66-0f9a-4267-95a1-71872f181779		16	19	24.05185185185185	15.912962962962963	24.09444444444444	12.122222222222224	0.95	0.3	0	3.7909800174170543	f	none
1211	93e3ba66-0f9a-4267-95a1-71872f181779		19	16	24.09444444444444	12.122222222222224	24.05185185185185	15.912962962962963	0.95	0.3	0	3.7909800174170543	f	none
1212	93e3ba66-0f9a-4267-95a1-71872f181779		19	17	24.09444444444444	12.122222222222224	24.009259259259256	8.331481481481482	0.95	0.3	0	3.7916977568480714	f	none
1213	93e3ba66-0f9a-4267-95a1-71872f181779		17	19	24.009259259259256	8.331481481481482	24.09444444444444	12.122222222222224	0.95	0.3	0	3.7916977568480714	f	none
1214	93e3ba66-0f9a-4267-95a1-71872f181779		17	18	24.009259259259256	8.331481481481482	23.966666666666665	3.901851851851852	0.95	0.3	0	4.429834396976539	f	none
1215	93e3ba66-0f9a-4267-95a1-71872f181779		18	17	23.966666666666665	3.901851851851852	24.009259259259256	8.331481481481482	0.95	0.3	0	4.429834396976539	f	none
1216	93e3ba66-0f9a-4267-95a1-71872f181779		18	3	23.966666666666665	3.901851851851852	18.003703703703703	1.9851851851851876	0.95	0.3	0	6.263428646418759	f	none
1217	93e3ba66-0f9a-4267-95a1-71872f181779		3	18	18.003703703703703	1.9851851851851876	23.966666666666665	3.901851851851852	0.95	0.3	0	6.263428646418759	f	none
1218	93e3ba66-0f9a-4267-95a1-71872f181779		4	18	17.918518518518518	6.031481481481482	23.966666666666665	3.901851851851852	0.95	0.3	0	6.412130564901521	f	none
1219	93e3ba66-0f9a-4267-95a1-71872f181779		18	4	23.966666666666665	3.901851851851852	17.918518518518518	6.031481481481482	0.95	0.3	0	6.412130564901521	f	none
1220	93e3ba66-0f9a-4267-95a1-71872f181779		17	4	24.009259259259256	8.331481481481482	17.918518518518518	6.031481481481482	0.95	0.3	0	6.510539360983777	f	none
1221	93e3ba66-0f9a-4267-95a1-71872f181779		4	17	17.918518518518518	6.031481481481482	24.009259259259256	8.331481481481482	0.95	0.3	0	6.510539360983777	f	none
1222	93e3ba66-0f9a-4267-95a1-71872f181779		13	12	2.074074074074075	18.085185185185185	2.2018518518518526	14.081481481481482	0.95	0.3	0	4.005742191847171	f	none
1223	93e3ba66-0f9a-4267-95a1-71872f181779		12	13	2.2018518518518526	14.081481481481482	2.074074074074075	18.085185185185185	0.95	0.3	0	4.005742191847171	f	none
1224	93e3ba66-0f9a-4267-95a1-71872f181779		9	17	18.003703703703703	9.992592592592594	24.009259259259256	8.331481481481482	0.95	0.3	0	6.23105028500982	f	none
1225	93e3ba66-0f9a-4267-95a1-71872f181779		17	9	24.009259259259256	8.331481481481482	18.003703703703703	9.992592592592594	0.95	0.3	0	6.23105028500982	f	none
1226	93e3ba66-0f9a-4267-95a1-71872f181779		19	9	24.09444444444444	12.122222222222224	18.003703703703703	9.992592592592594	0.95	0.3	0	6.452320910363609	f	none
1227	93e3ba66-0f9a-4267-95a1-71872f181779		9	19	18.003703703703703	9.992592592592594	24.09444444444444	12.122222222222224	0.95	0.3	0	6.452320910363609	f	none
1228	93e3ba66-0f9a-4267-95a1-71872f181779		10	19	17.961111111111112	13.911111111111111	24.09444444444444	12.122222222222224	0.95	0.3	0	6.388888888888885	f	none
1229	93e3ba66-0f9a-4267-95a1-71872f181779		19	10	24.09444444444444	12.122222222222224	17.961111111111112	13.911111111111111	0.95	0.3	0	6.388888888888885	f	none
1230	93e3ba66-0f9a-4267-95a1-71872f181779		16	10	24.05185185185185	15.912962962962963	17.961111111111112	13.911111111111111	0.95	0.3	0	6.411281744525171	f	none
1231	93e3ba66-0f9a-4267-95a1-71872f181779		10	16	17.961111111111112	13.911111111111111	24.05185185185185	15.912962962962963	0.95	0.3	0	6.411281744525171	f	none
1232	93e3ba66-0f9a-4267-95a1-71872f181779		16	20	24.05185185185185	15.912962962962963	29.929629629629627	13.996296296296297	0.95	0.3	0	6.182384872850393	f	none
1233	93e3ba66-0f9a-4267-95a1-71872f181779		20	16	29.929629629629627	13.996296296296297	24.05185185185185	15.912962962962963	0.95	0.3	0	6.182384872850393	f	none
1234	93e3ba66-0f9a-4267-95a1-71872f181779		20	19	29.929629629629627	13.996296296296297	24.09444444444444	12.122222222222224	0.95	0.3	0	6.128746999225965	f	none
1235	93e3ba66-0f9a-4267-95a1-71872f181779		19	20	24.09444444444444	12.122222222222224	29.929629629629627	13.996296296296297	0.95	0.3	0	6.128746999225965	f	none
1236	93e3ba66-0f9a-4267-95a1-71872f181779		19	21	24.09444444444444	12.122222222222224	30.014814814814812	9.992592592592594	0.95	0.3	0	6.291749175051072	f	none
1237	93e3ba66-0f9a-4267-95a1-71872f181779		21	19	30.014814814814812	9.992592592592594	24.09444444444444	12.122222222222224	0.95	0.3	0	6.291749175051072	f	none
1238	93e3ba66-0f9a-4267-95a1-71872f181779		21	17	30.014814814814812	9.992592592592594	24.009259259259256	8.331481481481482	0.95	0.3	0	6.2310502850098235	f	none
1239	93e3ba66-0f9a-4267-95a1-71872f181779		17	21	24.009259259259256	8.331481481481482	30.014814814814812	9.992592592592594	0.95	0.3	0	6.2310502850098235	f	none
1240	93e3ba66-0f9a-4267-95a1-71872f181779		17	22	24.009259259259256	8.331481481481482	29.972222222222218	6.329629629629631	0.95	0.3	0	6.290018929576501	f	none
1241	93e3ba66-0f9a-4267-95a1-71872f181779		22	17	29.972222222222218	6.329629629629631	24.009259259259256	8.331481481481482	0.95	0.3	0	6.290018929576501	f	none
1242	93e3ba66-0f9a-4267-95a1-71872f181779		22	18	29.972222222222218	6.329629629629631	23.966666666666665	3.901851851851852	0.95	0.3	0	6.477715837325359	f	none
1243	93e3ba66-0f9a-4267-95a1-71872f181779		18	22	23.966666666666665	3.901851851851852	29.972222222222218	6.329629629629631	0.95	0.3	0	6.477715837325359	f	none
1244	93e3ba66-0f9a-4267-95a1-71872f181779		14	11	9.953703703703704	18.085185185185185	9.911111111111111	13.996296296296297	0.95	0.3	0	4.08911071929127	f	none
1245	93e3ba66-0f9a-4267-95a1-71872f181779		11	14	9.911111111111111	13.996296296296297	9.953703703703704	18.085185185185185	0.95	0.3	0	4.08911071929127	f	none
1246	93e3ba66-0f9a-4267-95a1-71872f181779		22	23	29.972222222222218	6.329629629629631	35.89259259259259	9.907407407407408	0.95	0.3	0	6.917461900836169	f	none
1247	93e3ba66-0f9a-4267-95a1-71872f181779		23	22	35.89259259259259	9.907407407407408	29.972222222222218	6.329629629629631	0.95	0.3	0	6.917461900836169	f	none
1248	93e3ba66-0f9a-4267-95a1-71872f181779		23	20	35.89259259259259	9.907407407407408	29.929629629629627	13.996296296296297	0.95	0.3	0	7.230210207410783	f	none
1249	93e3ba66-0f9a-4267-95a1-71872f181779		20	23	29.929629629629627	13.996296296296297	35.89259259259259	9.907407407407408	0.95	0.3	0	7.230210207410783	f	none
1250	93e3ba66-0f9a-4267-95a1-71872f181779		20	21	29.929629629629627	13.996296296296297	30.014814814814812	9.992592592592594	0.95	0.3	0	4.004609826540631	f	none
1251	93e3ba66-0f9a-4267-95a1-71872f181779		21	20	30.014814814814812	9.992592592592594	29.929629629629627	13.996296296296297	0.95	0.3	0	4.004609826540631	f	none
1252	93e3ba66-0f9a-4267-95a1-71872f181779		21	22	30.014814814814812	9.992592592592594	29.972222222222218	6.329629629629631	0.95	0.3	0	3.6632105859453628	f	none
1253	93e3ba66-0f9a-4267-95a1-71872f181779		22	21	29.972222222222218	6.329629629629631	30.014814814814812	9.992592592592594	0.95	0.3	0	3.6632105859453628	f	none
1254	93e3ba66-0f9a-4267-95a1-71872f181779		21	23	30.014814814814812	9.992592592592594	35.89259259259259	9.907407407407408	0.95	0.3	0	5.878395029318235	f	none
1255	93e3ba66-0f9a-4267-95a1-71872f181779		23	21	35.89259259259259	9.907407407407408	30.014814814814812	9.992592592592594	0.95	0.3	0	5.878395029318235	f	none
1256	93e3ba66-0f9a-4267-95a1-71872f181779		11	8	9.911111111111111	13.996296296296297	9.996296296296297	9.822222222222223	0.95	0.3	0	4.174943220168673	f	none
1257	93e3ba66-0f9a-4267-95a1-71872f181779		8	11	9.996296296296297	9.822222222222223	9.911111111111111	13.996296296296297	0.95	0.3	0	4.174943220168673	f	none
1258	93e3ba66-0f9a-4267-95a1-71872f181779		12	7	2.2018518518518526	14.081481481481482	1.9462962962962969	9.907407407407408	0.95	0.3	0	4.181889885904774	f	none
1259	93e3ba66-0f9a-4267-95a1-71872f181779		7	12	1.9462962962962969	9.907407407407408	2.2018518518518526	14.081481481481482	0.95	0.3	0	4.181889885904774	f	none
1260	93e3ba66-0f9a-4267-95a1-71872f181779		7	6	1.9462962962962969	9.907407407407408	2.15925925925926	6.031481481481482	0.95	0.3	0	3.8817721477256644	f	none
1261	93e3ba66-0f9a-4267-95a1-71872f181779		6	7	2.15925925925926	6.031481481481482	1.9462962962962969	9.907407407407408	0.95	0.3	0	3.8817721477256644	f	none
1262	93e3ba66-0f9a-4267-95a1-71872f181779		6	5	2.15925925925926	6.031481481481482	10.081481481481482	6.116666666666667	0.95	0.3	0	7.9226801938514875	f	none
1263	93e3ba66-0f9a-4267-95a1-71872f181779		5	6	10.081481481481482	6.116666666666667	2.15925925925926	6.031481481481482	0.95	0.3	0	7.9226801938514875	f	none
1264	93e3ba66-0f9a-4267-95a1-71872f181779		8	5	9.996296296296297	9.822222222222223	10.081481481481482	6.116666666666667	0.95	0.3	0	3.7065345662874476	f	none
1265	93e3ba66-0f9a-4267-95a1-71872f181779		5	8	10.081481481481482	6.116666666666667	9.996296296296297	9.822222222222223	0.95	0.3	0	3.7065345662874476	f	none
1266	d2c251b5-9798-40c9-af25-0a8ec2f24833		13	14	2.074074074074075	18.085185185185185	9.953703703703704	18.085185185185185	0.95	0.3	0	7.87962962962963	f	none
1267	d2c251b5-9798-40c9-af25-0a8ec2f24833		14	13	9.953703703703704	18.085185185185185	2.074074074074075	18.085185185185185	0.95	0.3	0	7.87962962962963	f	none
1268	d2c251b5-9798-40c9-af25-0a8ec2f24833		8	7	9.996296296296297	9.822222222222223	1.9462962962962969	9.907407407407408	0.95	0.3	0	8.050450702648583	f	none
1269	d2c251b5-9798-40c9-af25-0a8ec2f24833		7	8	1.9462962962962969	9.907407407407408	9.996296296296297	9.822222222222223	0.95	0.3	0	8.050450702648583	f	none
1270	d2c251b5-9798-40c9-af25-0a8ec2f24833		6	1	2.15925925925926	6.031481481481482	1.9462962962962969	1.942592592592593	0.95	0.3	0	4.094431043414088	f	none
1271	d2c251b5-9798-40c9-af25-0a8ec2f24833		1	6	1.9462962962962969	1.942592592592593	2.15925925925926	6.031481481481482	0.95	0.3	0	4.094431043414088	f	none
1272	d2c251b5-9798-40c9-af25-0a8ec2f24833		5	2	10.081481481481482	6.116666666666667	9.953703703703704	1.9851851851851876	0.95	0.3	0	4.133456954211357	f	none
1273	d2c251b5-9798-40c9-af25-0a8ec2f24833		2	5	9.953703703703704	1.9851851851851876	10.081481481481482	6.116666666666667	0.95	0.3	0	4.133456954211357	f	none
1274	d2c251b5-9798-40c9-af25-0a8ec2f24833		1	2	1.9462962962962969	1.942592592592593	9.953703703703704	1.9851851851851876	0.95	0.3	0	8.007520684777953	f	none
1275	d2c251b5-9798-40c9-af25-0a8ec2f24833		2	1	9.953703703703704	1.9851851851851876	1.9462962962962969	1.942592592592593	0.95	0.3	0	8.007520684777953	f	none
1276	d2c251b5-9798-40c9-af25-0a8ec2f24833		2	3	9.953703703703704	1.9851851851851876	18.003703703703703	1.9851851851851876	0.95	0.3	0	8.049999999999999	f	none
1277	d2c251b5-9798-40c9-af25-0a8ec2f24833		3	2	18.003703703703703	1.9851851851851876	9.953703703703704	1.9851851851851876	0.95	0.3	0	8.049999999999999	f	none
1278	d2c251b5-9798-40c9-af25-0a8ec2f24833		3	4	18.003703703703703	1.9851851851851876	17.918518518518518	6.031481481481482	0.95	0.3	0	4.047192883122343	f	none
1279	d2c251b5-9798-40c9-af25-0a8ec2f24833		4	3	17.918518518518518	6.031481481481482	18.003703703703703	1.9851851851851876	0.95	0.3	0	4.047192883122343	f	none
1280	d2c251b5-9798-40c9-af25-0a8ec2f24833		4	5	17.918518518518518	6.031481481481482	10.081481481481482	6.116666666666667	0.95	0.3	0	7.837499986326333	f	none
1281	d2c251b5-9798-40c9-af25-0a8ec2f24833		5	4	10.081481481481482	6.116666666666667	17.918518518518518	6.031481481481482	0.95	0.3	0	7.837499986326333	f	none
1282	d2c251b5-9798-40c9-af25-0a8ec2f24833		4	9	17.918518518518518	6.031481481481482	18.003703703703703	9.992592592592594	0.95	0.3	0	3.9620269749640706	f	none
1283	d2c251b5-9798-40c9-af25-0a8ec2f24833		9	4	18.003703703703703	9.992592592592594	17.918518518518518	6.031481481481482	0.95	0.3	0	3.9620269749640706	f	none
1284	d2c251b5-9798-40c9-af25-0a8ec2f24833		9	8	18.003703703703703	9.992592592592594	9.996296296296297	9.822222222222223	0.95	0.3	0	8.009219653081262	f	none
1285	d2c251b5-9798-40c9-af25-0a8ec2f24833		8	9	9.996296296296297	9.822222222222223	18.003703703703703	9.992592592592594	0.95	0.3	0	8.009219653081262	f	none
1286	d2c251b5-9798-40c9-af25-0a8ec2f24833		10	9	17.961111111111112	13.911111111111111	18.003703703703703	9.992592592592594	0.95	0.3	0	3.9187499931631664	f	none
1287	d2c251b5-9798-40c9-af25-0a8ec2f24833		9	10	18.003703703703703	9.992592592592594	17.961111111111112	13.911111111111111	0.95	0.3	0	3.9187499931631664	f	none
1288	d2c251b5-9798-40c9-af25-0a8ec2f24833		11	12	9.911111111111111	13.996296296296297	2.2018518518518526	14.081481481481482	0.95	0.3	0	7.709729881276623	f	none
1289	d2c251b5-9798-40c9-af25-0a8ec2f24833		12	11	2.2018518518518526	14.081481481481482	9.911111111111111	13.996296296296297	0.95	0.3	0	7.709729881276623	f	none
1290	d2c251b5-9798-40c9-af25-0a8ec2f24833		11	10	9.911111111111111	13.996296296296297	17.961111111111112	13.911111111111111	0.95	0.3	0	8.050450702648583	f	none
1291	d2c251b5-9798-40c9-af25-0a8ec2f24833		10	11	17.961111111111112	13.911111111111111	9.911111111111111	13.996296296296297	0.95	0.3	0	8.050450702648583	f	none
1292	d2c251b5-9798-40c9-af25-0a8ec2f24833		10	15	17.961111111111112	13.911111111111111	17.833333333333332	17.914814814814815	0.95	0.3	0	4.005742191847171	f	none
1293	d2c251b5-9798-40c9-af25-0a8ec2f24833		15	10	17.833333333333332	17.914814814814815	17.961111111111112	13.911111111111111	0.95	0.3	0	4.005742191847171	f	none
1294	d2c251b5-9798-40c9-af25-0a8ec2f24833		14	15	9.953703703703704	18.085185185185185	17.833333333333332	17.914814814814815	0.95	0.3	0	7.8814712562590294	f	none
1295	d2c251b5-9798-40c9-af25-0a8ec2f24833		15	14	17.833333333333332	17.914814814814815	9.953703703703704	18.085185185185185	0.95	0.3	0	7.8814712562590294	f	none
1296	d2c251b5-9798-40c9-af25-0a8ec2f24833		15	16	17.833333333333332	17.914814814814815	24.05185185185185	15.912962962962963	0.95	0.3	0	6.532792925075801	f	none
1297	d2c251b5-9798-40c9-af25-0a8ec2f24833		16	15	24.05185185185185	15.912962962962963	17.833333333333332	17.914814814814815	0.95	0.3	0	6.532792925075801	f	none
1298	d2c251b5-9798-40c9-af25-0a8ec2f24833		16	19	24.05185185185185	15.912962962962963	24.09444444444444	12.122222222222224	0.95	0.3	0	3.7909800174170543	f	none
1299	d2c251b5-9798-40c9-af25-0a8ec2f24833		19	16	24.09444444444444	12.122222222222224	24.05185185185185	15.912962962962963	0.95	0.3	0	3.7909800174170543	f	none
1300	d2c251b5-9798-40c9-af25-0a8ec2f24833		19	17	24.09444444444444	12.122222222222224	24.009259259259256	8.331481481481482	0.95	0.3	0	3.7916977568480714	f	none
1301	d2c251b5-9798-40c9-af25-0a8ec2f24833		17	19	24.009259259259256	8.331481481481482	24.09444444444444	12.122222222222224	0.95	0.3	0	3.7916977568480714	f	none
1302	d2c251b5-9798-40c9-af25-0a8ec2f24833		17	18	24.009259259259256	8.331481481481482	23.966666666666665	3.901851851851852	0.95	0.3	0	4.429834396976539	f	none
1303	d2c251b5-9798-40c9-af25-0a8ec2f24833		18	17	23.966666666666665	3.901851851851852	24.009259259259256	8.331481481481482	0.95	0.3	0	4.429834396976539	f	none
1304	d2c251b5-9798-40c9-af25-0a8ec2f24833		18	3	23.966666666666665	3.901851851851852	18.003703703703703	1.9851851851851876	0.95	0.3	0	6.263428646418759	f	none
1305	d2c251b5-9798-40c9-af25-0a8ec2f24833		3	18	18.003703703703703	1.9851851851851876	23.966666666666665	3.901851851851852	0.95	0.3	0	6.263428646418759	f	none
1306	d2c251b5-9798-40c9-af25-0a8ec2f24833		4	18	17.918518518518518	6.031481481481482	23.966666666666665	3.901851851851852	0.95	0.3	0	6.412130564901521	f	none
1307	d2c251b5-9798-40c9-af25-0a8ec2f24833		18	4	23.966666666666665	3.901851851851852	17.918518518518518	6.031481481481482	0.95	0.3	0	6.412130564901521	f	none
1308	d2c251b5-9798-40c9-af25-0a8ec2f24833		17	4	24.009259259259256	8.331481481481482	17.918518518518518	6.031481481481482	0.95	0.3	0	6.510539360983777	f	none
1309	d2c251b5-9798-40c9-af25-0a8ec2f24833		4	17	17.918518518518518	6.031481481481482	24.009259259259256	8.331481481481482	0.95	0.3	0	6.510539360983777	f	none
1310	d2c251b5-9798-40c9-af25-0a8ec2f24833		13	12	2.074074074074075	18.085185185185185	2.2018518518518526	14.081481481481482	0.95	0.3	0	4.005742191847171	f	none
1311	d2c251b5-9798-40c9-af25-0a8ec2f24833		12	13	2.2018518518518526	14.081481481481482	2.074074074074075	18.085185185185185	0.95	0.3	0	4.005742191847171	f	none
1312	d2c251b5-9798-40c9-af25-0a8ec2f24833		9	17	18.003703703703703	9.992592592592594	24.009259259259256	8.331481481481482	0.95	0.3	0	6.23105028500982	f	none
1313	d2c251b5-9798-40c9-af25-0a8ec2f24833		17	9	24.009259259259256	8.331481481481482	18.003703703703703	9.992592592592594	0.95	0.3	0	6.23105028500982	f	none
1314	d2c251b5-9798-40c9-af25-0a8ec2f24833		19	9	24.09444444444444	12.122222222222224	18.003703703703703	9.992592592592594	0.95	0.3	0	6.452320910363609	f	none
1315	d2c251b5-9798-40c9-af25-0a8ec2f24833		9	19	18.003703703703703	9.992592592592594	24.09444444444444	12.122222222222224	0.95	0.3	0	6.452320910363609	f	none
1316	d2c251b5-9798-40c9-af25-0a8ec2f24833		10	19	17.961111111111112	13.911111111111111	24.09444444444444	12.122222222222224	0.95	0.3	0	6.388888888888885	f	none
1317	d2c251b5-9798-40c9-af25-0a8ec2f24833		19	10	24.09444444444444	12.122222222222224	17.961111111111112	13.911111111111111	0.95	0.3	0	6.388888888888885	f	none
1318	d2c251b5-9798-40c9-af25-0a8ec2f24833		16	10	24.05185185185185	15.912962962962963	17.961111111111112	13.911111111111111	0.95	0.3	0	6.411281744525171	f	none
1319	d2c251b5-9798-40c9-af25-0a8ec2f24833		10	16	17.961111111111112	13.911111111111111	24.05185185185185	15.912962962962963	0.95	0.3	0	6.411281744525171	f	none
1320	d2c251b5-9798-40c9-af25-0a8ec2f24833		16	20	24.05185185185185	15.912962962962963	29.929629629629627	13.996296296296297	0.95	0.3	0	6.182384872850393	f	none
1321	d2c251b5-9798-40c9-af25-0a8ec2f24833		20	16	29.929629629629627	13.996296296296297	24.05185185185185	15.912962962962963	0.95	0.3	0	6.182384872850393	f	none
1322	d2c251b5-9798-40c9-af25-0a8ec2f24833		20	19	29.929629629629627	13.996296296296297	24.09444444444444	12.122222222222224	0.95	0.3	0	6.128746999225965	f	none
1323	d2c251b5-9798-40c9-af25-0a8ec2f24833		19	20	24.09444444444444	12.122222222222224	29.929629629629627	13.996296296296297	0.95	0.3	0	6.128746999225965	f	none
1324	d2c251b5-9798-40c9-af25-0a8ec2f24833		19	21	24.09444444444444	12.122222222222224	30.014814814814812	9.992592592592594	0.95	0.3	0	6.291749175051072	f	none
1325	d2c251b5-9798-40c9-af25-0a8ec2f24833		21	19	30.014814814814812	9.992592592592594	24.09444444444444	12.122222222222224	0.95	0.3	0	6.291749175051072	f	none
1326	d2c251b5-9798-40c9-af25-0a8ec2f24833		21	17	30.014814814814812	9.992592592592594	24.009259259259256	8.331481481481482	0.95	0.3	0	6.2310502850098235	f	none
1327	d2c251b5-9798-40c9-af25-0a8ec2f24833		17	21	24.009259259259256	8.331481481481482	30.014814814814812	9.992592592592594	0.95	0.3	0	6.2310502850098235	f	none
1328	d2c251b5-9798-40c9-af25-0a8ec2f24833		17	22	24.009259259259256	8.331481481481482	29.972222222222218	6.329629629629631	0.95	0.3	0	6.290018929576501	f	none
1329	d2c251b5-9798-40c9-af25-0a8ec2f24833		22	17	29.972222222222218	6.329629629629631	24.009259259259256	8.331481481481482	0.95	0.3	0	6.290018929576501	f	none
1330	d2c251b5-9798-40c9-af25-0a8ec2f24833		22	18	29.972222222222218	6.329629629629631	23.966666666666665	3.901851851851852	0.95	0.3	0	6.477715837325359	f	none
1331	d2c251b5-9798-40c9-af25-0a8ec2f24833		18	22	23.966666666666665	3.901851851851852	29.972222222222218	6.329629629629631	0.95	0.3	0	6.477715837325359	f	none
1332	d2c251b5-9798-40c9-af25-0a8ec2f24833		14	11	9.953703703703704	18.085185185185185	9.911111111111111	13.996296296296297	0.95	0.3	0	4.08911071929127	f	none
1333	d2c251b5-9798-40c9-af25-0a8ec2f24833		11	14	9.911111111111111	13.996296296296297	9.953703703703704	18.085185185185185	0.95	0.3	0	4.08911071929127	f	none
1334	d2c251b5-9798-40c9-af25-0a8ec2f24833		22	23	29.972222222222218	6.329629629629631	35.89259259259259	9.907407407407408	0.95	0.3	0	6.917461900836169	f	none
1335	d2c251b5-9798-40c9-af25-0a8ec2f24833		23	22	35.89259259259259	9.907407407407408	29.972222222222218	6.329629629629631	0.95	0.3	0	6.917461900836169	f	none
1336	d2c251b5-9798-40c9-af25-0a8ec2f24833		23	20	35.89259259259259	9.907407407407408	29.929629629629627	13.996296296296297	0.95	0.3	0	7.230210207410783	f	none
1337	d2c251b5-9798-40c9-af25-0a8ec2f24833		20	23	29.929629629629627	13.996296296296297	35.89259259259259	9.907407407407408	0.95	0.3	0	7.230210207410783	f	none
1338	d2c251b5-9798-40c9-af25-0a8ec2f24833		20	21	29.929629629629627	13.996296296296297	30.014814814814812	9.992592592592594	0.95	0.3	0	4.004609826540631	f	none
1339	d2c251b5-9798-40c9-af25-0a8ec2f24833		21	20	30.014814814814812	9.992592592592594	29.929629629629627	13.996296296296297	0.95	0.3	0	4.004609826540631	f	none
1340	d2c251b5-9798-40c9-af25-0a8ec2f24833		21	22	30.014814814814812	9.992592592592594	29.972222222222218	6.329629629629631	0.95	0.3	0	3.6632105859453628	f	none
1341	d2c251b5-9798-40c9-af25-0a8ec2f24833		22	21	29.972222222222218	6.329629629629631	30.014814814814812	9.992592592592594	0.95	0.3	0	3.6632105859453628	f	none
1342	d2c251b5-9798-40c9-af25-0a8ec2f24833		21	23	30.014814814814812	9.992592592592594	35.89259259259259	9.907407407407408	0.95	0.3	0	5.878395029318235	f	none
1343	d2c251b5-9798-40c9-af25-0a8ec2f24833		23	21	35.89259259259259	9.907407407407408	30.014814814814812	9.992592592592594	0.95	0.3	0	5.878395029318235	f	none
1344	d2c251b5-9798-40c9-af25-0a8ec2f24833		11	8	9.911111111111111	13.996296296296297	9.996296296296297	9.822222222222223	0.95	0.3	0	4.174943220168673	f	none
1345	d2c251b5-9798-40c9-af25-0a8ec2f24833		8	11	9.996296296296297	9.822222222222223	9.911111111111111	13.996296296296297	0.95	0.3	0	4.174943220168673	f	none
1346	d2c251b5-9798-40c9-af25-0a8ec2f24833		12	7	2.2018518518518526	14.081481481481482	1.9462962962962969	9.907407407407408	0.95	0.3	0	4.181889885904774	f	none
1347	d2c251b5-9798-40c9-af25-0a8ec2f24833		7	12	1.9462962962962969	9.907407407407408	2.2018518518518526	14.081481481481482	0.95	0.3	0	4.181889885904774	f	none
1348	d2c251b5-9798-40c9-af25-0a8ec2f24833		7	6	1.9462962962962969	9.907407407407408	2.15925925925926	6.031481481481482	0.95	0.3	0	3.8817721477256644	f	none
1349	d2c251b5-9798-40c9-af25-0a8ec2f24833		6	7	2.15925925925926	6.031481481481482	1.9462962962962969	9.907407407407408	0.95	0.3	0	3.8817721477256644	f	none
1350	d2c251b5-9798-40c9-af25-0a8ec2f24833		6	5	2.15925925925926	6.031481481481482	10.081481481481482	6.116666666666667	0.95	0.3	0	7.9226801938514875	f	none
1351	d2c251b5-9798-40c9-af25-0a8ec2f24833		5	6	10.081481481481482	6.116666666666667	2.15925925925926	6.031481481481482	0.95	0.3	0	7.9226801938514875	f	none
1352	d2c251b5-9798-40c9-af25-0a8ec2f24833		8	5	9.996296296296297	9.822222222222223	10.081481481481482	6.116666666666667	0.95	0.3	0	3.7065345662874476	f	none
1353	d2c251b5-9798-40c9-af25-0a8ec2f24833		5	8	10.081481481481482	6.116666666666667	9.996296296296297	9.822222222222223	0.95	0.3	0	3.7065345662874476	f	none
1354	bb0dae6d-91cc-417d-9493-08beebeec142		13	14	2.074	18.085	9.954	18.085	0.95	0.3	0	7.880000000000001	f	none
1355	bb0dae6d-91cc-417d-9493-08beebeec142		14	13	9.954	18.085	2.074	18.085	0.95	0.3	0	7.880000000000001	f	none
1356	bb0dae6d-91cc-417d-9493-08beebeec142		8	7	9.996	9.822	1.946	9.907	0.95	0.3	0	8.050448745256379	f	none
1357	bb0dae6d-91cc-417d-9493-08beebeec142		7	8	1.946	9.907	9.996	9.822	0.95	0.3	0	8.050448745256379	f	none
1358	bb0dae6d-91cc-417d-9493-08beebeec142		6	1	2.159	6.031	1.946	1.943	0.95	0.3	0	4.09354528495777	f	none
1359	bb0dae6d-91cc-417d-9493-08beebeec142		1	6	1.946	1.943	2.159	6.031	0.95	0.3	0	4.09354528495777	f	none
1360	bb0dae6d-91cc-417d-9493-08beebeec142		5	2	10.081	6.117	9.954	1.985	0.95	0.3	0	4.133951257574283	f	none
1361	bb0dae6d-91cc-417d-9493-08beebeec142		2	5	9.954	1.985	10.081	6.117	0.95	0.3	0	4.133951257574283	f	none
1362	bb0dae6d-91cc-417d-9493-08beebeec142		1	2	1.946	1.943	9.954	1.985	0.95	0.3	0	8.008110139102735	f	none
1363	bb0dae6d-91cc-417d-9493-08beebeec142		2	1	9.954	1.985	1.946	1.943	0.95	0.3	0	8.008110139102735	f	none
1364	bb0dae6d-91cc-417d-9493-08beebeec142		2	3	9.954	1.985	18.004	1.985	0.95	0.3	0	8.05	f	none
1365	bb0dae6d-91cc-417d-9493-08beebeec142		3	2	18.004	1.985	9.954	1.985	0.95	0.3	0	8.05	f	none
1366	bb0dae6d-91cc-417d-9493-08beebeec142		3	4	18.004	1.985	17.919	6.031	0.95	0.3	0	4.046892758648293	f	none
1367	bb0dae6d-91cc-417d-9493-08beebeec142		4	3	17.919	6.031	18.004	1.985	0.95	0.3	0	4.046892758648293	f	none
1368	bb0dae6d-91cc-417d-9493-08beebeec142		4	5	17.919	6.031	10.081	6.117	0.95	0.3	0	7.838471789832506	f	none
1369	bb0dae6d-91cc-417d-9493-08beebeec142		5	4	10.081	6.117	17.919	6.031	0.95	0.3	0	7.838471789832506	f	none
1370	bb0dae6d-91cc-417d-9493-08beebeec142		4	9	17.919	6.031	18.004	9.993	0.95	0.3	0	3.9629116820842736	f	none
1371	bb0dae6d-91cc-417d-9493-08beebeec142		9	4	18.004	9.993	17.919	6.031	0.95	0.3	0	3.9629116820842736	f	none
1372	bb0dae6d-91cc-417d-9493-08beebeec142		9	8	18.004	9.993	9.996	9.822	0.95	0.3	0	8.009825528686628	f	none
1373	bb0dae6d-91cc-417d-9493-08beebeec142		8	9	9.996	9.822	18.004	9.993	0.95	0.3	0	8.009825528686628	f	none
1374	bb0dae6d-91cc-417d-9493-08beebeec142		10	9	17.961	13.911	18.004	9.993	0.95	0.3	0	3.9182359551206196	f	none
1375	bb0dae6d-91cc-417d-9493-08beebeec142		9	10	18.004	9.993	17.961	13.911	0.95	0.3	0	3.9182359551206196	f	none
1376	bb0dae6d-91cc-417d-9493-08beebeec142		11	12	9.911	13.996	2.202	14.081	0.95	0.3	0	7.709468593878569	f	none
1377	bb0dae6d-91cc-417d-9493-08beebeec142		12	11	2.202	14.081	9.911	13.996	0.95	0.3	0	7.709468593878569	f	none
1378	bb0dae6d-91cc-417d-9493-08beebeec142		11	10	9.911	13.996	17.961	13.911	0.95	0.3	0	8.050448745256377	f	none
1379	bb0dae6d-91cc-417d-9493-08beebeec142		10	11	17.961	13.911	9.911	13.996	0.95	0.3	0	8.050448745256377	f	none
1380	bb0dae6d-91cc-417d-9493-08beebeec142		10	15	17.961	13.911	17.833	17.915	0.95	0.3	0	4.006045431594604	f	none
1381	bb0dae6d-91cc-417d-9493-08beebeec142		15	10	17.833	17.915	17.961	13.911	0.95	0.3	0	4.006045431594604	f	none
1382	bb0dae6d-91cc-417d-9493-08beebeec142		14	15	9.954	18.085	17.833	17.915	0.95	0.3	0	7.880833775686426	f	none
1383	bb0dae6d-91cc-417d-9493-08beebeec142		15	14	17.833	17.915	9.954	18.085	0.95	0.3	0	7.880833775686426	f	none
1384	bb0dae6d-91cc-417d-9493-08beebeec142		15	16	17.833	17.915	24.052	15.913	0.95	0.3	0	6.533296641053428	f	none
1385	bb0dae6d-91cc-417d-9493-08beebeec142		16	15	24.052	15.913	17.833	17.915	0.95	0.3	0	6.533296641053428	f	none
1386	bb0dae6d-91cc-417d-9493-08beebeec142		16	19	24.052	15.913	24.094	12.122	0.95	0.3	0	3.7912326491525157	f	none
1387	bb0dae6d-91cc-417d-9493-08beebeec142		19	16	24.094	12.122	24.052	15.913	0.95	0.3	0	3.7912326491525157	f	none
1388	bb0dae6d-91cc-417d-9493-08beebeec142		19	17	24.094	12.122	24.009	8.331	0.95	0.3	0	3.7919527950648333	f	none
1389	bb0dae6d-91cc-417d-9493-08beebeec142		17	19	24.009	8.331	24.094	12.122	0.95	0.3	0	3.7919527950648333	f	none
1390	bb0dae6d-91cc-417d-9493-08beebeec142		17	18	24.009	8.331	23.967	3.902	0.95	0.3	0	4.4291991375416835	f	none
1391	bb0dae6d-91cc-417d-9493-08beebeec142		18	17	23.967	3.902	24.009	8.331	0.95	0.3	0	4.4291991375416835	f	none
1392	bb0dae6d-91cc-417d-9493-08beebeec142		18	3	23.967	3.902	18.004	1.985	0.95	0.3	0	6.263565917271085	f	none
1393	bb0dae6d-91cc-417d-9493-08beebeec142		3	18	18.004	1.985	23.967	3.902	0.95	0.3	0	6.263565917271085	f	none
1394	bb0dae6d-91cc-417d-9493-08beebeec142		4	18	17.919	6.031	23.967	3.902	0.95	0.3	0	6.411781733652509	f	none
1395	bb0dae6d-91cc-417d-9493-08beebeec142		18	4	23.967	3.902	17.919	6.031	0.95	0.3	0	6.411781733652509	f	none
1396	bb0dae6d-91cc-417d-9493-08beebeec142		17	4	24.009	8.331	17.919	6.031	0.95	0.3	0	6.509846388356641	f	none
1397	bb0dae6d-91cc-417d-9493-08beebeec142		4	17	17.919	6.031	24.009	8.331	0.95	0.3	0	6.509846388356641	f	none
1398	bb0dae6d-91cc-417d-9493-08beebeec142		13	12	2.074	18.085	2.202	14.081	0.95	0.3	0	4.006045431594606	f	none
1399	bb0dae6d-91cc-417d-9493-08beebeec142		12	13	2.202	14.081	2.074	18.085	0.95	0.3	0	4.006045431594606	f	none
1400	bb0dae6d-91cc-417d-9493-08beebeec142		9	17	18.004	9.993	24.009	8.331	0.95	0.3	0	6.230751880792558	f	none
1401	bb0dae6d-91cc-417d-9493-08beebeec142		17	9	24.009	8.331	18.004	9.993	0.95	0.3	0	6.230751880792558	f	none
1402	bb0dae6d-91cc-417d-9493-08beebeec142		19	9	24.094	12.122	18.004	9.993	0.95	0.3	0	6.451413876042987	f	none
1403	bb0dae6d-91cc-417d-9493-08beebeec142		9	19	18.004	9.993	24.094	12.122	0.95	0.3	0	6.451413876042987	f	none
1404	bb0dae6d-91cc-417d-9493-08beebeec142		10	19	17.961	13.911	24.094	12.122	0.95	0.3	0	6.388600003130579	f	none
1405	bb0dae6d-91cc-417d-9493-08beebeec142		19	10	24.094	12.122	17.961	13.911	0.95	0.3	0	6.388600003130579	f	none
1406	bb0dae6d-91cc-417d-9493-08beebeec142		16	10	24.052	15.913	17.961	13.911	0.95	0.3	0	6.411574299655274	f	none
1407	bb0dae6d-91cc-417d-9493-08beebeec142		10	16	17.961	13.911	24.052	15.913	0.95	0.3	0	6.411574299655274	f	none
1408	bb0dae6d-91cc-417d-9493-08beebeec142		16	20	24.052	15.913	29.93	13.996	0.95	0.3	0	6.18269949132254	f	none
1409	bb0dae6d-91cc-417d-9493-08beebeec142		20	16	29.93	13.996	24.052	15.913	0.95	0.3	0	6.18269949132254	f	none
1410	bb0dae6d-91cc-417d-9493-08beebeec142		20	19	29.93	13.996	24.094	12.122	0.95	0.3	0	6.129500142752261	f	none
1411	bb0dae6d-91cc-417d-9493-08beebeec142		19	20	24.094	12.122	29.93	13.996	0.95	0.3	0	6.129500142752261	f	none
1412	bb0dae6d-91cc-417d-9493-08beebeec142		19	21	24.094	12.122	30.015	9.993	0.95	0.3	0	6.292128574655797	f	none
1413	bb0dae6d-91cc-417d-9493-08beebeec142		21	19	30.015	9.993	24.094	12.122	0.95	0.3	0	6.292128574655797	f	none
1414	bb0dae6d-91cc-417d-9493-08beebeec142		21	17	30.015	9.993	24.009	8.331	0.95	0.3	0	6.231715654617114	f	none
1415	bb0dae6d-91cc-417d-9493-08beebeec142		17	21	24.009	8.331	30.015	9.993	0.95	0.3	0	6.231715654617114	f	none
1416	bb0dae6d-91cc-417d-9493-08beebeec142		17	22	24.009	8.331	29.972	6.33	0.95	0.3	0	6.289782985127548	f	none
1417	bb0dae6d-91cc-417d-9493-08beebeec142		22	17	29.972	6.33	24.009	8.331	0.95	0.3	0	6.289782985127548	f	none
1418	bb0dae6d-91cc-417d-9493-08beebeec142		22	18	29.972	6.33	23.967	3.902	0.95	0.3	0	6.477284075907126	f	none
1419	bb0dae6d-91cc-417d-9493-08beebeec142		18	22	23.967	3.902	29.972	6.33	0.95	0.3	0	6.477284075907126	f	none
1420	bb0dae6d-91cc-417d-9493-08beebeec142		14	11	9.954	18.085	9.911	13.996	0.95	0.3	0	4.089226088149199	f	none
1421	bb0dae6d-91cc-417d-9493-08beebeec142		11	14	9.911	13.996	9.954	18.085	0.95	0.3	0	4.089226088149199	f	none
1422	bb0dae6d-91cc-417d-9493-08beebeec142		22	23	29.972	6.33	35.893	9.907	0.95	0.3	0	6.917598571758844	f	none
1423	bb0dae6d-91cc-417d-9493-08beebeec142		23	22	35.893	9.907	29.972	6.33	0.95	0.3	0	6.917598571758844	f	none
1424	bb0dae6d-91cc-417d-9493-08beebeec142		23	20	35.893	9.907	29.93	13.996	0.95	0.3	0	7.230303589753339	f	none
1425	bb0dae6d-91cc-417d-9493-08beebeec142		20	23	29.93	13.996	35.893	9.907	0.95	0.3	0	7.230303589753339	f	none
1426	bb0dae6d-91cc-417d-9493-08beebeec142		20	21	29.93	13.996	30.015	9.993	0.95	0.3	0	4.003902346461512	f	none
1427	bb0dae6d-91cc-417d-9493-08beebeec142		21	20	30.015	9.993	29.93	13.996	0.95	0.3	0	4.003902346461512	f	none
1428	bb0dae6d-91cc-417d-9493-08beebeec142		21	22	30.015	9.993	29.972	6.33	0.95	0.3	0	3.663252380057918	f	none
1429	bb0dae6d-91cc-417d-9493-08beebeec142		22	21	29.972	6.33	30.015	9.993	0.95	0.3	0	3.663252380057918	f	none
1430	bb0dae6d-91cc-417d-9493-08beebeec142		21	23	30.015	9.993	35.893	9.907	0.95	0.3	0	5.878629091888686	f	none
1431	bb0dae6d-91cc-417d-9493-08beebeec142		23	21	35.893	9.907	30.015	9.993	0.95	0.3	0	5.878629091888686	f	none
1432	bb0dae6d-91cc-417d-9493-08beebeec142		11	8	9.911	13.996	9.996	9.822	0.95	0.3	0	4.174865387051421	f	none
1433	bb0dae6d-91cc-417d-9493-08beebeec142		8	11	9.996	9.822	9.911	13.996	0.95	0.3	0	4.174865387051421	f	none
1434	bb0dae6d-91cc-417d-9493-08beebeec142		12	7	2.202	14.081	1.946	9.907	0.95	0.3	0	4.181843134312906	f	none
1435	bb0dae6d-91cc-417d-9493-08beebeec142		7	12	1.946	9.907	2.202	14.081	0.95	0.3	0	4.181843134312906	f	none
1436	bb0dae6d-91cc-417d-9493-08beebeec142		7	6	1.946	9.907	2.159	6.031	0.95	0.3	0	3.8818481423157194	f	none
1437	bb0dae6d-91cc-417d-9493-08beebeec142		6	7	2.159	6.031	1.946	9.907	0.95	0.3	0	3.8818481423157194	f	none
1438	bb0dae6d-91cc-417d-9493-08beebeec142		6	5	2.159	6.031	10.081	6.117	0.95	0.3	0	7.922466787560551	f	none
1439	bb0dae6d-91cc-417d-9493-08beebeec142		5	6	10.081	6.117	2.159	6.031	0.95	0.3	0	7.922466787560551	f	none
1440	bb0dae6d-91cc-417d-9493-08beebeec142		8	5	9.996	9.822	10.081	6.117	0.95	0.3	0	3.705974905473591	f	none
1441	bb0dae6d-91cc-417d-9493-08beebeec142		5	8	10.081	6.117	9.996	9.822	0.95	0.3	0	3.705974905473591	f	none
1442	9a861d33-52f1-4fa1-83d5-76da8fad400a		1	2	2	2	6	2	0.95	0.3	0	4	f	none
1443	9a861d33-52f1-4fa1-83d5-76da8fad400a		2	1	6	2	2	2	0.95	0.3	0	4	f	none
1444	9a861d33-52f1-4fa1-83d5-76da8fad400a		12	13	6	10	10	10	0.95	0.3	0	4	f	none
1445	9a861d33-52f1-4fa1-83d5-76da8fad400a		13	12	10	10	6	10	0.95	0.3	0	4	f	none
1446	9a861d33-52f1-4fa1-83d5-76da8fad400a		13	14	10	10	14	10	0.95	0.3	0	4	f	none
1447	9a861d33-52f1-4fa1-83d5-76da8fad400a		14	13	14	10	10	10	0.95	0.3	0	4	f	none
1448	9a861d33-52f1-4fa1-83d5-76da8fad400a		14	15	14	10	18	10	0.95	0.3	0	4	f	none
1449	9a861d33-52f1-4fa1-83d5-76da8fad400a		15	14	18	10	14	10	0.95	0.3	0	4	f	none
1450	9a861d33-52f1-4fa1-83d5-76da8fad400a		1	6	2	2	2	6	0.95	0.3	0	4	f	none
1451	9a861d33-52f1-4fa1-83d5-76da8fad400a		6	1	2	6	2	2	0.95	0.3	0	4	f	none
1452	9a861d33-52f1-4fa1-83d5-76da8fad400a		6	11	2	6	2	10	0.95	0.3	0	4	f	none
1453	9a861d33-52f1-4fa1-83d5-76da8fad400a		11	6	2	10	2	6	0.95	0.3	0	4	f	none
1454	9a861d33-52f1-4fa1-83d5-76da8fad400a		2	7	6	2	6	6	0.95	0.3	0	4	f	none
1455	9a861d33-52f1-4fa1-83d5-76da8fad400a		7	2	6	6	6	2	0.95	0.3	0	4	f	none
1456	9a861d33-52f1-4fa1-83d5-76da8fad400a		7	12	6	6	6	10	0.95	0.3	0	4	f	none
1457	9a861d33-52f1-4fa1-83d5-76da8fad400a		12	7	6	10	6	6	0.95	0.3	0	4	f	none
1458	9a861d33-52f1-4fa1-83d5-76da8fad400a		3	8	10	2	10	6	0.95	0.3	0	4	f	none
1459	9a861d33-52f1-4fa1-83d5-76da8fad400a		8	3	10	6	10	2	0.95	0.3	0	4	f	none
1460	9a861d33-52f1-4fa1-83d5-76da8fad400a		8	13	10	6	10	10	0.95	0.3	0	4	f	none
1461	9a861d33-52f1-4fa1-83d5-76da8fad400a		13	8	10	10	10	6	0.95	0.3	0	4	f	none
1462	9a861d33-52f1-4fa1-83d5-76da8fad400a		4	9	14	2	14	6	0.95	0.3	0	4	f	none
1463	9a861d33-52f1-4fa1-83d5-76da8fad400a		9	4	14	6	14	2	0.95	0.3	0	4	f	none
1464	9a861d33-52f1-4fa1-83d5-76da8fad400a		2	3	6	2	10	2	0.95	0.3	0	4	f	none
1465	9a861d33-52f1-4fa1-83d5-76da8fad400a		3	2	10	2	6	2	0.95	0.3	0	4	f	none
1466	9a861d33-52f1-4fa1-83d5-76da8fad400a		9	14	14	6	14	10	0.95	0.3	0	4	f	none
1467	9a861d33-52f1-4fa1-83d5-76da8fad400a		14	9	14	10	14	6	0.95	0.3	0	4	f	none
1468	9a861d33-52f1-4fa1-83d5-76da8fad400a		5	10	18	2	18	6	0.95	0.3	0	4	f	none
1469	9a861d33-52f1-4fa1-83d5-76da8fad400a		10	5	18	6	18	2	0.95	0.3	0	4	f	none
1470	9a861d33-52f1-4fa1-83d5-76da8fad400a		10	15	18	6	18	10	0.95	0.3	0	4	f	none
1471	9a861d33-52f1-4fa1-83d5-76da8fad400a		15	10	18	10	18	6	0.95	0.3	0	4	f	none
1472	9a861d33-52f1-4fa1-83d5-76da8fad400a		16	17	10	6	14	6	0.95	0.3	0	4	f	none
1473	9a861d33-52f1-4fa1-83d5-76da8fad400a		17	16	14	6	10	6	0.95	0.3	0	4	f	none
1474	9a861d33-52f1-4fa1-83d5-76da8fad400a		16	18	10	6	10	10	0.95	0.3	0	4	f	none
1475	9a861d33-52f1-4fa1-83d5-76da8fad400a		18	16	10	10	10	6	0.95	0.3	0	4	f	none
1476	9a861d33-52f1-4fa1-83d5-76da8fad400a		18	19	10	10	14	10	0.95	0.3	0	4	f	none
1477	9a861d33-52f1-4fa1-83d5-76da8fad400a		19	18	14	10	10	10	0.95	0.3	0	4	f	none
1478	9a861d33-52f1-4fa1-83d5-76da8fad400a		19	20	14	10	18	10	0.95	0.3	0	4	f	none
1479	9a861d33-52f1-4fa1-83d5-76da8fad400a		20	19	18	10	14	10	0.95	0.3	0	4	f	none
1480	9a861d33-52f1-4fa1-83d5-76da8fad400a		17	19	14	6	14	10	0.95	0.3	0	4	f	none
1481	9a861d33-52f1-4fa1-83d5-76da8fad400a		19	17	14	10	14	6	0.95	0.3	0	4	f	none
1482	9a861d33-52f1-4fa1-83d5-76da8fad400a		3	4	10	2	14	2	0.95	0.3	0	4	f	none
1483	9a861d33-52f1-4fa1-83d5-76da8fad400a		4	3	14	2	10	2	0.95	0.3	0	4	f	none
1484	9a861d33-52f1-4fa1-83d5-76da8fad400a		4	5	14	2	18	2	0.95	0.3	0	4	f	none
1485	9a861d33-52f1-4fa1-83d5-76da8fad400a		5	4	18	2	14	2	0.95	0.3	0	4	f	none
1486	9a861d33-52f1-4fa1-83d5-76da8fad400a		6	7	2	6	6	6	0.95	0.3	0	4	f	none
1487	9a861d33-52f1-4fa1-83d5-76da8fad400a		7	6	6	6	2	6	0.95	0.3	0	4	f	none
1488	9a861d33-52f1-4fa1-83d5-76da8fad400a		7	8	6	6	10	6	0.95	0.3	0	4	f	none
1489	9a861d33-52f1-4fa1-83d5-76da8fad400a		8	7	10	6	6	6	0.95	0.3	0	4	f	none
1490	9a861d33-52f1-4fa1-83d5-76da8fad400a		8	9	10	6	14	6	0.95	0.3	0	4	f	none
1491	9a861d33-52f1-4fa1-83d5-76da8fad400a		9	8	14	6	10	6	0.95	0.3	0	4	f	none
1492	9a861d33-52f1-4fa1-83d5-76da8fad400a		9	10	14	6	18	6	0.95	0.3	0	4	f	none
1493	9a861d33-52f1-4fa1-83d5-76da8fad400a		10	9	18	6	14	6	0.95	0.3	0	4	f	none
1494	9a861d33-52f1-4fa1-83d5-76da8fad400a		11	12	2	10	6	10	0.95	0.3	0	4	f	none
1495	9a861d33-52f1-4fa1-83d5-76da8fad400a		12	11	6	10	2	10	0.95	0.3	0	4	f	none
1496	cc51d003-010b-4a2d-8879-f312e80b2cfd		1	2	2	2	6	2	0.95	0.3	0	4	f	none
1497	cc51d003-010b-4a2d-8879-f312e80b2cfd		2	1	6	2	2	2	0.95	0.3	0	4	f	none
1498	cc51d003-010b-4a2d-8879-f312e80b2cfd		12	13	6	10	10	10	0.95	0.3	0	4	f	none
1499	cc51d003-010b-4a2d-8879-f312e80b2cfd		13	12	10	10	6	10	0.95	0.3	0	4	f	none
1500	cc51d003-010b-4a2d-8879-f312e80b2cfd		13	14	10	10	14	10	0.95	0.3	0	4	f	none
1501	cc51d003-010b-4a2d-8879-f312e80b2cfd		14	13	14	10	10	10	0.95	0.3	0	4	f	none
1502	cc51d003-010b-4a2d-8879-f312e80b2cfd		14	15	14	10	18	10	0.95	0.3	0	4	f	none
1503	cc51d003-010b-4a2d-8879-f312e80b2cfd		15	14	18	10	14	10	0.95	0.3	0	4	f	none
1504	cc51d003-010b-4a2d-8879-f312e80b2cfd		1	6	2	2	2	6	0.95	0.3	0	4	f	none
1505	cc51d003-010b-4a2d-8879-f312e80b2cfd		6	1	2	6	2	2	0.95	0.3	0	4	f	none
1506	cc51d003-010b-4a2d-8879-f312e80b2cfd		6	11	2	6	2	10	0.95	0.3	0	4	f	none
1507	cc51d003-010b-4a2d-8879-f312e80b2cfd		11	6	2	10	2	6	0.95	0.3	0	4	f	none
1508	cc51d003-010b-4a2d-8879-f312e80b2cfd		2	7	6	2	6	6	0.95	0.3	0	4	f	none
1509	cc51d003-010b-4a2d-8879-f312e80b2cfd		7	2	6	6	6	2	0.95	0.3	0	4	f	none
1510	cc51d003-010b-4a2d-8879-f312e80b2cfd		7	12	6	6	6	10	0.95	0.3	0	4	f	none
1511	cc51d003-010b-4a2d-8879-f312e80b2cfd		12	7	6	10	6	6	0.95	0.3	0	4	f	none
1512	cc51d003-010b-4a2d-8879-f312e80b2cfd		3	8	10	2	10	6	0.95	0.3	0	4	f	none
1513	cc51d003-010b-4a2d-8879-f312e80b2cfd		8	3	10	6	10	2	0.95	0.3	0	4	f	none
1514	cc51d003-010b-4a2d-8879-f312e80b2cfd		8	13	10	6	10	10	0.95	0.3	0	4	f	none
1515	cc51d003-010b-4a2d-8879-f312e80b2cfd		13	8	10	10	10	6	0.95	0.3	0	4	f	none
1516	cc51d003-010b-4a2d-8879-f312e80b2cfd		4	9	14	2	14	6	0.95	0.3	0	4	f	none
1517	cc51d003-010b-4a2d-8879-f312e80b2cfd		9	4	14	6	14	2	0.95	0.3	0	4	f	none
1518	cc51d003-010b-4a2d-8879-f312e80b2cfd		2	3	6	2	10	2	0.95	0.3	0	4	f	none
1519	cc51d003-010b-4a2d-8879-f312e80b2cfd		3	2	10	2	6	2	0.95	0.3	0	4	f	none
1520	cc51d003-010b-4a2d-8879-f312e80b2cfd		9	14	14	6	14	10	0.95	0.3	0	4	f	none
1521	cc51d003-010b-4a2d-8879-f312e80b2cfd		14	9	14	10	14	6	0.95	0.3	0	4	f	none
1522	cc51d003-010b-4a2d-8879-f312e80b2cfd		5	10	18	2	18	6	0.95	0.3	0	4	f	none
1523	cc51d003-010b-4a2d-8879-f312e80b2cfd		10	5	18	6	18	2	0.95	0.3	0	4	f	none
1524	cc51d003-010b-4a2d-8879-f312e80b2cfd		10	15	18	6	18	10	0.95	0.3	0	4	f	none
1525	cc51d003-010b-4a2d-8879-f312e80b2cfd		15	10	18	10	18	6	0.95	0.3	0	4	f	none
1526	cc51d003-010b-4a2d-8879-f312e80b2cfd		16	17	10	6	14	6	0.95	0.3	0	4	f	none
1527	cc51d003-010b-4a2d-8879-f312e80b2cfd		17	16	14	6	10	6	0.95	0.3	0	4	f	none
1528	cc51d003-010b-4a2d-8879-f312e80b2cfd		16	18	10	6	10	10	0.95	0.3	0	4	f	none
1529	cc51d003-010b-4a2d-8879-f312e80b2cfd		18	16	10	10	10	6	0.95	0.3	0	4	f	none
1530	cc51d003-010b-4a2d-8879-f312e80b2cfd		18	19	10	10	14	10	0.95	0.3	0	4	f	none
1531	cc51d003-010b-4a2d-8879-f312e80b2cfd		19	18	14	10	10	10	0.95	0.3	0	4	f	none
1532	cc51d003-010b-4a2d-8879-f312e80b2cfd		19	20	14	10	18	10	0.95	0.3	0	4	f	none
1533	cc51d003-010b-4a2d-8879-f312e80b2cfd		20	19	18	10	14	10	0.95	0.3	0	4	f	none
1534	cc51d003-010b-4a2d-8879-f312e80b2cfd		17	19	14	6	14	10	0.95	0.3	0	4	f	none
1535	cc51d003-010b-4a2d-8879-f312e80b2cfd		19	17	14	10	14	6	0.95	0.3	0	4	f	none
1536	cc51d003-010b-4a2d-8879-f312e80b2cfd		3	4	10	2	14	2	0.95	0.3	0	4	f	none
1537	cc51d003-010b-4a2d-8879-f312e80b2cfd		4	3	14	2	10	2	0.95	0.3	0	4	f	none
1538	cc51d003-010b-4a2d-8879-f312e80b2cfd		4	5	14	2	18	2	0.95	0.3	0	4	f	none
1539	cc51d003-010b-4a2d-8879-f312e80b2cfd		5	4	18	2	14	2	0.95	0.3	0	4	f	none
1540	cc51d003-010b-4a2d-8879-f312e80b2cfd		6	7	2	6	6	6	0.95	0.3	0	4	f	none
1541	cc51d003-010b-4a2d-8879-f312e80b2cfd		7	6	6	6	2	6	0.95	0.3	0	4	f	none
1542	cc51d003-010b-4a2d-8879-f312e80b2cfd		7	8	6	6	10	6	0.95	0.3	0	4	f	none
1543	cc51d003-010b-4a2d-8879-f312e80b2cfd		8	7	10	6	6	6	0.95	0.3	0	4	f	none
1544	cc51d003-010b-4a2d-8879-f312e80b2cfd		8	9	10	6	14	6	0.95	0.3	0	4	f	none
1545	cc51d003-010b-4a2d-8879-f312e80b2cfd		9	8	14	6	10	6	0.95	0.3	0	4	f	none
1546	cc51d003-010b-4a2d-8879-f312e80b2cfd		9	10	14	6	18	6	0.95	0.3	0	4	f	none
1547	cc51d003-010b-4a2d-8879-f312e80b2cfd		10	9	18	6	14	6	0.95	0.3	0	4	f	none
1548	cc51d003-010b-4a2d-8879-f312e80b2cfd		11	12	2	10	6	10	0.95	0.3	0	4	f	none
1549	cc51d003-010b-4a2d-8879-f312e80b2cfd		12	11	6	10	2	10	0.95	0.3	0	4	f	none
3615	1779790224391		15	9	61	-85	-17	-85	0.95	0.4	0	78	f	none
3616	1779790224391		12	10	-264	-85	-186	-85	0.95	0.5	2	78	f	none
3617	1779790224391		10	2	-186	-85	-186	-4	0.95	0.4	0	81	f	none
3618	1779790224391		2	14	-186	-4	-186	80	0.95	0.4	0	84	f	none
3619	1779790224391		2	1	-186	-4	-264	-4	0.95	0.4	0	78	f	none
3620	1779790224391		1	12	-264	-4	-264	-85	0.95	0.4	1	81	f	none
3621	1779790224391		1	13	-264	-4	-264	83	0.95	0.4	0	87	f	none
3622	1779790224391		3	11	-361	-4	-361	-85	0.95	0.5	0	81	f	none
3623	1779790224391		11	69	-361	-85	-309	-85	0.95	0.5	0	52	f	none
3624	1779790224391		69	12	-309	-85	-264	-85	0.95	0.5	0	45	f	none
3625	1779790224391		1	96	-264	-4	-309	-4	0.95	0.4	0	45	f	none
3626	1779790224391		96	3	-309	-4	-361	-4	0.95	0.5	0	52	f	none
3627	1779790224391		2	64	-186	-4	-137	-4	0.95	0.4	0	49	f	none
3628	1779790224391		64	19	-137	-4	-80	-4	0.95	0.4	0	57	f	none
3629	1779790224391		19	4	-80	-4	-17	-4	0.95	0.4	0	63	f	none
3630	1779790224391		6	7	316	-4	316	-85	0.95	0.4	0	81	f	none
3631	1779790224391		9	4	-17	-85	-17	-4	0.95	0.4	0	81	f	none
3632	1779790224391		8	5	148	-85	148	-4	0.95	0.4	0	81	f	none
3633	1779790224391		4	18	-17	-4	61	-4	0.95	0.4	0	78	f	none
3634	1779790224391		18	5	61	-4	148	-4	0.95	0.4	0	87	f	none
3635	1779790224391		5	17	148	-4	240	-4	0.95	0.4	0	92	f	none
3636	1779790224391		17	6	240	-4	316	-4	0.95	0.4	0	76	f	none
3637	1779790224391		7	16	316	-85	240	-85	0.95	0.4	0	76	f	none
3638	1779790224391		8	15	148	-85	61	-85	0.95	0.5	0	87	f	none
1638	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	13	14	2.074	18.085	9.954	18.085	0.95	0.3	0	7.880000000000001	f	none
1639	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	14	13	9.954	18.085	2.074	18.085	0.95	0.3	0	7.880000000000001	f	none
1640	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	8	7	9.996	9.822	1.946	9.907	0.95	0.3	0	8.050448745256379	f	none
1641	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	7	8	1.946	9.907	9.996	9.822	0.95	0.3	0	8.050448745256379	f	none
1642	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	6	1	2.159	6.031	1.946	1.943	0.95	0.3	0	4.09354528495777	f	none
1643	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	1	6	1.946	1.943	2.159	6.031	0.95	0.3	0	4.09354528495777	f	none
1644	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	5	2	10.081	6.117	9.954	1.985	0.95	0.3	0	4.133951257574283	f	none
1645	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	2	5	9.954	1.985	10.081	6.117	0.95	0.3	0	4.133951257574283	f	none
1646	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	1	2	1.946	1.943	9.954	1.985	0.95	0.3	0	8.008110139102735	f	none
1647	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	2	1	9.954	1.985	1.946	1.943	0.95	0.3	0	8.008110139102735	f	none
1648	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	2	3	9.954	1.985	18.004	1.985	0.95	0.3	0	8.05	f	none
1649	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	3	2	18.004	1.985	9.954	1.985	0.95	0.3	0	8.05	f	none
1650	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	3	4	18.004	1.985	17.919	6.031	0.95	0.3	0	4.046892758648293	f	none
1651	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	4	3	17.919	6.031	18.004	1.985	0.95	0.3	0	4.046892758648293	f	none
1652	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	4	5	17.919	6.031	10.081	6.117	0.95	0.3	0	7.838471789832506	f	none
1653	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	5	4	10.081	6.117	17.919	6.031	0.95	0.3	0	7.838471789832506	f	none
1654	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	4	9	17.919	6.031	18.004	9.993	0.95	0.3	0	3.9629116820842736	f	none
1655	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	9	4	18.004	9.993	17.919	6.031	0.95	0.3	0	3.9629116820842736	f	none
1656	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	9	8	18.004	9.993	9.996	9.822	0.95	0.3	0	8.009825528686628	f	none
1657	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	8	9	9.996	9.822	18.004	9.993	0.95	0.3	0	8.009825528686628	f	none
1658	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	10	9	17.961	13.911	18.004	9.993	0.95	0.3	0	3.9182359551206196	f	none
1659	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	9	10	18.004	9.993	17.961	13.911	0.95	0.3	0	3.9182359551206196	f	none
1660	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	11	12	9.911	13.996	2.202	14.081	0.95	0.3	0	7.709468593878569	f	none
1661	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	12	11	2.202	14.081	9.911	13.996	0.95	0.3	0	7.709468593878569	f	none
1662	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	11	10	9.911	13.996	17.961	13.911	0.95	0.3	0	8.050448745256377	f	none
1663	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	10	11	17.961	13.911	9.911	13.996	0.95	0.3	0	8.050448745256377	f	none
1664	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	10	15	17.961	13.911	17.833	17.915	0.95	0.3	0	4.006045431594604	f	none
1665	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	15	10	17.833	17.915	17.961	13.911	0.95	0.3	0	4.006045431594604	f	none
1666	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	14	15	9.954	18.085	17.833	17.915	0.95	0.3	0	7.880833775686426	f	none
1667	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	15	14	17.833	17.915	9.954	18.085	0.95	0.3	0	7.880833775686426	f	none
1668	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	15	16	17.833	17.915	24.052	15.913	0.95	0.3	0	6.533296641053428	f	none
1669	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	16	15	24.052	15.913	17.833	17.915	0.95	0.3	0	6.533296641053428	f	none
1670	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	16	19	24.052	15.913	24.094	12.122	0.95	0.3	0	3.7912326491525157	f	none
1671	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	19	16	24.094	12.122	24.052	15.913	0.95	0.3	0	3.7912326491525157	f	none
1672	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	19	17	24.094	12.122	24.009	8.331	0.95	0.3	0	3.7919527950648333	f	none
1673	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	17	19	24.009	8.331	24.094	12.122	0.95	0.3	0	3.7919527950648333	f	none
1674	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	17	18	24.009	8.331	23.967	3.902	0.95	0.3	0	4.4291991375416835	f	none
1675	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	18	17	23.967	3.902	24.009	8.331	0.95	0.3	0	4.4291991375416835	f	none
1676	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	18	3	23.967	3.902	18.004	1.985	0.95	0.3	0	6.263565917271085	f	none
1677	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	3	18	18.004	1.985	23.967	3.902	0.95	0.3	0	6.263565917271085	f	none
1678	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	4	18	17.919	6.031	23.967	3.902	0.95	0.3	0	6.411781733652509	f	none
1679	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	18	4	23.967	3.902	17.919	6.031	0.95	0.3	0	6.411781733652509	f	none
1680	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	17	4	24.009	8.331	17.919	6.031	0.95	0.3	0	6.509846388356641	f	none
1681	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	4	17	17.919	6.031	24.009	8.331	0.95	0.3	0	6.509846388356641	f	none
1682	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	13	12	2.074	18.085	2.202	14.081	0.95	0.3	0	4.006045431594606	f	none
1683	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	12	13	2.202	14.081	2.074	18.085	0.95	0.3	0	4.006045431594606	f	none
1684	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	9	17	18.004	9.993	24.009	8.331	0.95	0.3	0	6.230751880792558	f	none
1685	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	17	9	24.009	8.331	18.004	9.993	0.95	0.3	0	6.230751880792558	f	none
1686	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	19	9	24.094	12.122	18.004	9.993	0.95	0.3	0	6.451413876042987	f	none
1687	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	9	19	18.004	9.993	24.094	12.122	0.95	0.3	0	6.451413876042987	f	none
1688	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	10	19	17.961	13.911	24.094	12.122	0.95	0.3	0	6.388600003130579	f	none
1689	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	19	10	24.094	12.122	17.961	13.911	0.95	0.3	0	6.388600003130579	f	none
1690	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	16	10	24.052	15.913	17.961	13.911	0.95	0.3	0	6.411574299655274	f	none
1691	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	10	16	17.961	13.911	24.052	15.913	0.95	0.3	0	6.411574299655274	f	none
1692	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	16	20	24.052	15.913	29.93	13.996	0.95	0.3	0	6.18269949132254	f	none
1693	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	20	16	29.93	13.996	24.052	15.913	0.95	0.3	0	6.18269949132254	f	none
1694	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	20	19	29.93	13.996	24.094	12.122	0.95	0.3	0	6.129500142752261	f	none
1695	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	19	20	24.094	12.122	29.93	13.996	0.95	0.3	0	6.129500142752261	f	none
1696	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	19	21	24.094	12.122	30.015	9.993	0.95	0.3	0	6.292128574655797	f	none
1697	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	21	19	30.015	9.993	24.094	12.122	0.95	0.3	0	6.292128574655797	f	none
1698	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	21	17	30.015	9.993	24.009	8.331	0.95	0.3	0	6.231715654617114	f	none
1699	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	17	21	24.009	8.331	30.015	9.993	0.95	0.3	0	6.231715654617114	f	none
1700	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	17	22	24.009	8.331	29.972	6.33	0.95	0.3	0	6.289782985127548	f	none
1701	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	22	17	29.972	6.33	24.009	8.331	0.95	0.3	0	6.289782985127548	f	none
1702	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	22	18	29.972	6.33	23.967	3.902	0.95	0.3	0	6.477284075907126	f	none
1703	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	18	22	23.967	3.902	29.972	6.33	0.95	0.3	0	6.477284075907126	f	none
1704	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	14	11	9.954	18.085	9.911	13.996	0.95	0.3	0	4.089226088149199	f	none
1705	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	11	14	9.911	13.996	9.954	18.085	0.95	0.3	0	4.089226088149199	f	none
1706	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	22	23	29.972	6.33	35.893	9.907	0.95	0.3	0	6.917598571758844	f	none
1707	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	23	22	35.893	9.907	29.972	6.33	0.95	0.3	0	6.917598571758844	f	none
1708	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	23	20	35.893	9.907	29.93	13.996	0.95	0.3	0	7.230303589753339	f	none
1709	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	20	23	29.93	13.996	35.893	9.907	0.95	0.3	0	7.230303589753339	f	none
1710	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	20	21	29.93	13.996	30.015	9.993	0.95	0.3	0	4.003902346461512	f	none
1711	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	21	20	30.015	9.993	29.93	13.996	0.95	0.3	0	4.003902346461512	f	none
1712	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	21	22	30.015	9.993	29.972	6.33	0.95	0.3	0	3.663252380057918	f	none
1713	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	22	21	29.972	6.33	30.015	9.993	0.95	0.3	0	3.663252380057918	f	none
1714	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	21	23	30.015	9.993	35.893	9.907	0.95	0.3	0	5.878629091888686	f	none
1715	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	23	21	35.893	9.907	30.015	9.993	0.95	0.3	0	5.878629091888686	f	none
1716	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	11	8	9.911	13.996	9.996	9.822	0.95	0.3	0	4.174865387051421	f	none
1717	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	8	11	9.996	9.822	9.911	13.996	0.95	0.3	0	4.174865387051421	f	none
1718	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	12	7	2.202	14.081	1.946	9.907	0.95	0.3	0	4.181843134312906	f	none
1719	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	7	12	1.946	9.907	2.202	14.081	0.95	0.3	0	4.181843134312906	f	none
1720	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	7	6	1.946	9.907	2.159	6.031	0.95	0.3	0	3.8818481423157194	f	none
1721	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	6	7	2.159	6.031	1.946	9.907	0.95	0.3	0	3.8818481423157194	f	none
1722	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	6	5	2.159	6.031	10.081	6.117	0.95	0.3	0	7.922466787560551	f	none
1723	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	5	6	10.081	6.117	2.159	6.031	0.95	0.3	0	7.922466787560551	f	none
1724	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	8	5	9.996	9.822	10.081	6.117	0.95	0.3	0	3.705974905473591	f	none
1725	9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	5	8	10.081	6.117	9.996	9.822	0.95	0.3	0	3.705974905473591	f	none
1799	1779430599645		74	241	-320	-117	-320	-18	0.95	0.5	0	99	f	none
1800	1779430599645		241	264	-320	-18	-320	77	0.95	0.5	0	95	f	none
1801	1779430599645		264	225	-320	77	-41	77	0.95	0.5	0	279	f	none
1802	1779430599645		225	84	-41	77	197	77	0.95	0.5	0	238	f	none
1803	1779430599645		64	999	197	-117	197	-22	0.95	0.5	0	95	f	none
1804	1779430599645		999	84	197	-22	197	77	0.95	0.5	0	99	f	none
1805	1779430599645		74	21	-320	-117	-242	-117	0.95	0.4	0	78	f	none
1806	1779430599645		21	16	-242	-117	-154	-117	0.95	0.4	0	88	f	none
1807	1779430599645		16	14	-154	-117	26	-117	0.95	0.9	0	180	f	none
1808	1779430599645		14	41	26	-117	127	-117	0.95	0.9	0	101	f	none
1809	1779430599645		41	64	127	-117	197	-117	0.95	0.5	0	70	f	none
4744	1784004253436		12	13	245	235	245	344	0.95	0.6	0	109	f	none
4745	1784004253436		14	101	285	475	365	475	0.95	0.4	1	80	f	none
4746	1784004253436		101	102	365	475	445	475	0.95	0.4	1	80	f	none
4747	1784004253436		102	103	445	475	525	475	0.95	0.4	1	80	f	none
4748	1784004253436		21	81	5	155	69	155	0.95	0.3	0	64	f	none
4749	1784004253436		81	82	69	155	129	155	0.95	0.3	0	60	f	none
4750	1784004253436		82	22	129	155	195	155	0.95	0.3	0	66	f	none
4751	1784004253436		103	104	525	475	607	475	0.95	0.4	1	82	f	none
4752	1784004253436		104	15	607	475	686	475	0.95	0.3	1	79	f	none
4753	1784004253436		15	105	686	475	765	475	0.95	0.5	1	79	f	none
4754	1784004253436		15	20	686	475	686	396	0.95	0.3	1	79	f	none
4755	1784004253436		205	20	765	396	686	396	0.95	0.5	1	79	f	none
4756	1784004253436		20	204	686	396	608	396	0.95	0.3	1	78	f	none
4757	1784004253436		204	203	608	396	525	396	0.95	0.4	1	83	f	none
4758	1784004253436		106	107	845	475	931	475	0.95	0.6	1	86	f	none
4759	1784004253436		107	108	931	475	1025	475	0.95	0.6	1	94	f	none
4760	1784004253436		108	16	1025	475	1103	475	0.95	0.3	1	78	f	none
4761	1784004253436		16	109	1103	475	1168	475	0.95	0.5	1	65	f	none
4762	1784004253436		209	19	1165	396	1103	396	0.95	0.5	1	62	f	none
4763	1784004253436		19	208	1103	396	1025	396	0.95	0.4	1	78	f	none
4764	1784004253436		208	207	1025	396	931	396	0.95	0.6	1	94	f	none
4765	1784004253436		207	206	931	396	845	396	0.95	0.6	1	86	f	none
4766	1784004253436		16	19	1103	475	1103	396	0.95	0.3	1	79	f	none
4767	1784004253436		110	111	1245	475	1326	475	0.95	0.6	1	81	f	none
4768	1784004253436		111	112	1326	475	1403	475	0.95	0.6	1	77	f	none
4769	1784004253436		112	17	1403	475	1499	475	0.95	0.4	1	96	f	none
4770	1784004253436		17	18	1499	475	1499	396	0.95	0.4	1	79	f	none
4771	1784004253436		18	212	1499	396	1403	396	0.95	0.5	1	96	f	none
4772	1784004253436		212	211	1403	396	1326	396	0.95	0.5	1	77	f	none
4773	1784004253436		211	210	1326	396	1245	396	0.95	0.5	1	81	f	none
4774	1784004253436		105	106	765	475	845	475	0.95	0.6	1	80	f	none
4775	1784004253436		202	201	445	396	365	396	0.95	0.4	1	80	f	none
4776	1784004253436		203	202	525	396	445	396	0.95	0.4	1	80	f	none
4777	1784004253436		206	205	845	396	765	396	0.95	0.6	1	80	f	none
4778	1784004253436		210	209	1245	396	1165	396	0.95	0.6	1	80	f	none
4779	1784004253436		11	10	5	105	5	35	0.95	0.1	0	70	f	none
4780	1784004253436		21	11	5	155	5	105	0.95	0.2	0	50	f	none
4781	1784004253436		109	110	1168	475	1245	475	0.95	0.6	1	77	f	none
\.


--
-- Data for Name: agv_maps; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agv_maps (id, name, origin_x, origin_y, origin_theta, resolution, image_path, modify_time, layer, created_at, updated_at) FROM stdin;
9b09e29d-a1e3-4248-bbe1-ff55481cf4b8	map_demo	0	0	0	0.05	\N	2026-04-28 17:01:03+07	0	2026-04-28 16:33:14.155776+07	2026-04-28 17:01:03.171428+07
97	test_18_11	-27.558782958984377	-13.920159912109376	0	0.05	maps/97.png	2025-11-18 09:22:20+07	0	2025-11-18 09:27:08.329768+07	2025-11-18 13:27:30.841352+07
56	TNGF_TOT	-21.27944793701172	-22.536351013183594	0	0.05	maps/56.png	2025-06-20 15:18:09+07	0	2025-11-24 15:29:42.840341+07	2025-11-24 15:29:42.840341+07
98	tang_4	-24.72513122558594	-11.875196838378907	0	0.05	maps/98.png	2025-12-01 15:15:27+07	0	2025-12-01 15:23:51.581723+07	2025-12-03 15:00:44.848992+07
55	TNGF_20_6	-15.793310546875	-22.570196533203127	0	0.05	maps/55.png	2025-06-20 15:13:24+07	0	2026-03-02 16:16:13.518721+07	2026-03-02 16:16:13.518721+07
87	test_249	-27.821524047851565	-18.92806396484375	0	0.05	maps/87.png	2025-09-24 15:15:57+07	0	2026-03-02 16:16:38.739802+07	2026-03-02 16:16:38.739802+07
1784004253436	Võ Nhai 1	0	0	0	0.05	\N	2026-07-20 04:09:37+07	0	2026-07-14 11:44:13.460029+07	2026-07-20 11:09:37.456828+07
20	origin	0	0	0	0.05	maps/20.png	2024-06-04 14:46:57+07	0	2026-03-11 09:24:54.384391+07	2026-03-11 09:35:43.299028+07
59	TOT_23_6	-6.720140075683594	-9.081924438476562	0	0.05	maps/59.png	2025-06-23 14:41:57+07	0	2026-03-11 09:39:07.376699+07	2026-03-11 09:39:07.376699+07
99	T4_22_1	-13.717884826660157	-26.56014099121094	0	0.05	maps/99.png	2026-01-22 14:43:39+07	0	2026-03-02 16:14:41.826317+07	2026-03-17 14:05:19.602871+07
d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	map_d9dabec7-fbfa-48a7-a20b-5c4eaaf444ce	0	0	0	0.05	\N	2026-04-23 11:05:11.681578+07	0	2026-04-23 11:05:11.681923+07	2026-04-23 11:05:11.681923+07
4001ae10-9a25-4f79-9941-6bfc467df987	map_4001ae10-9a25-4f79-9941-6bfc467df987	0	0	0	0.05	\N	2026-04-28 13:37:56.217161+07	0	2026-04-28 13:37:56.218233+07	2026-04-28 13:37:56.218233+07
abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	map_abcfe5b0-8a1b-4b7a-bd0b-9904a50c7da8	0	0	0	0.05	\N	2026-04-28 13:37:59.695945+07	0	2026-04-28 13:37:59.696622+07	2026-04-28 13:37:59.696622+07
97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	map_97c66d8a-21f3-4a42-ba5c-295bd62bdfc0	0	0	0	0.05	\N	2026-04-28 13:38:00.256998+07	0	2026-04-28 13:38:00.25795+07	2026-04-28 13:38:00.25795+07
4656f23b-ed40-43d1-a314-94bbdedf5d29	map_4656f23b-ed40-43d1-a314-94bbdedf5d29	0	0	0	0.05	\N	2026-04-28 13:38:00.532778+07	0	2026-04-28 13:38:00.53402+07	2026-04-28 13:38:00.53402+07
ceed0bd3-7f76-46e4-b188-61010dcd100a	map_ceed0bd3-7f76-46e4-b188-61010dcd100a	0	0	0	0.05	\N	2026-04-28 13:38:00.697886+07	0	2026-04-28 13:38:00.699117+07	2026-04-28 13:38:00.699117+07
98162503-c3c3-452f-a896-e85ded516cb9	map_98162503-c3c3-452f-a896-e85ded516cb9	0	0	0	0.05	\N	2026-04-28 13:38:00.873497+07	0	2026-04-28 13:38:00.874717+07	2026-04-28 13:38:00.874717+07
b6fcdc48-990f-4dfd-a50e-2eabca664196	map_b6fcdc48-990f-4dfd-a50e-2eabca664196	0	0	0	0.05	\N	2026-04-28 13:38:01.029733+07	0	2026-04-28 13:38:01.03069+07	2026-04-28 13:38:01.03069+07
61d76858-93a2-413d-9840-ea136908c9ab	map_61d76858-93a2-413d-9840-ea136908c9ab	0	0	0	0.05	\N	2026-04-28 13:38:16.872435+07	0	2026-04-28 13:38:16.873586+07	2026-04-28 13:38:16.873586+07
f54ea27c-6e7d-4a6e-b45f-28e814b2e378	map_f54ea27c-6e7d-4a6e-b45f-28e814b2e378	0	0	0	0.05	\N	2026-04-28 13:38:17.054797+07	0	2026-04-28 13:38:17.055894+07	2026-04-28 13:38:17.055894+07
88173d83-9aa6-4df1-aaa8-c06b63569fc5	map_88173d83-9aa6-4df1-aaa8-c06b63569fc5	0	0	0	0.05	\N	2026-04-28 13:38:17.578097+07	0	2026-04-28 13:38:17.578679+07	2026-04-28 13:38:17.578679+07
b7badbae-9aaf-4f4a-9ed0-87096255212c	map_b7badbae-9aaf-4f4a-9ed0-87096255212c	0	0	0	0.05	\N	2026-04-28 13:38:17.762426+07	0	2026-04-28 13:38:17.762685+07	2026-04-28 13:38:17.762685+07
3772fe6a-6a43-4c30-a40e-125ddc5598c4	map_3772fe6a-6a43-4c30-a40e-125ddc5598c4	0	0	0	0.05	\N	2026-04-28 13:38:17.933866+07	0	2026-04-28 13:38:17.934723+07	2026-04-28 13:38:17.934723+07
37b3a676-aa46-4650-aa23-9fa08b2c9e4f	map_37b3a676-aa46-4650-aa23-9fa08b2c9e4f	0	0	0	0.05	\N	2026-04-28 13:38:18.117973+07	0	2026-04-28 13:38:18.118899+07	2026-04-28 13:38:18.118899+07
523fb5c2-e610-4f58-b471-646e295b8f15	map_523fb5c2-e610-4f58-b471-646e295b8f15	0	0	0	0.05	\N	2026-04-28 14:23:38.946557+07	0	2026-04-28 14:23:38.947036+07	2026-04-28 14:23:38.947036+07
93e3ba66-0f9a-4267-95a1-71872f181779	map_93e3ba66-0f9a-4267-95a1-71872f181779	0	0	0	0.05	\N	2026-04-28 14:39:36.00615+07	0	2026-04-28 14:39:36.007038+07	2026-04-28 14:39:36.007038+07
d2c251b5-9798-40c9-af25-0a8ec2f24833	map_d2c251b5-9798-40c9-af25-0a8ec2f24833	0	0	0	0.05	\N	2026-04-28 14:42:12.96916+07	0	2026-04-28 14:42:12.970012+07	2026-04-28 14:42:12.970012+07
bb0dae6d-91cc-417d-9493-08beebeec142	map_bb0dae6d-91cc-417d-9493-08beebeec142	0	0	0	0.05	\N	2026-04-28 14:46:47.077759+07	0	2026-04-28 14:46:47.078382+07	2026-04-28 14:46:47.078382+07
703c7452-55bb-4e15-8304-f4e88ddbc2ba	map_703c7452-55bb-4e15-8304-f4e88ddbc2ba	0	0	0	0.05	\N	2026-04-28 15:54:25.848448+07	0	2026-04-28 15:54:25.849475+07	2026-04-28 15:54:25.849475+07
9a861d33-52f1-4fa1-83d5-76da8fad400a	map_9a861d33-52f1-4fa1-83d5-76da8fad400a	0	0	0	0.05	\N	2026-04-28 15:59:02.028985+07	0	2026-04-28 15:59:02.029623+07	2026-04-28 15:59:02.029623+07
cc51d003-010b-4a2d-8879-f312e80b2cfd	map_cc51d003-010b-4a2d-8879-f312e80b2cfd	0	0	0	0.05	\N	2026-04-28 16:00:37.730346+07	0	2026-04-28 16:00:37.836284+07	2026-04-28 16:00:37.836284+07
cc16078b-cae9-40a3-ad3c-d74da64266f6	map_unknown	0	0	0	0.05	\N	2026-04-28 16:16:11.906933+07	0	2026-04-28 16:16:11.907765+07	2026-04-28 16:16:11.907765+07
80	new_map	0	0	0	0.05	\N	2026-04-28 16:20:13+07	0	2026-04-28 16:20:13.292599+07	2026-04-28 16:20:13.292599+07
1779430599645	AGV_test	0	0	0	0.05	\N	2026-05-26 06:52:08+07	0	2026-05-22 13:16:39.841484+07	2026-05-26 13:52:08.155749+07
1779790224391	Bản đồ mới	0	0	0	0.05	\N	2026-07-10 09:10:23+07	0	2026-05-26 17:10:24.732444+07	2026-07-10 16:10:23.992534+07
\.


--
-- Data for Name: agv_schedules; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agv_schedules (id, agv_id, command, team_id, priority, schedule_type, scheduled_at, time_of_day, days_of_week, interval_minutes, label, active, created_at, last_run, next_run, run_count, map_id) FROM stdin;
c9a4fa74120440d68486cf1bfd6877eb	AGV01	wf:312653cc-e6f2-4a8b-b4cf-1c9810ba2982	1	2	once	2026-06-03 08:50:00+07	\N	\N	\N	Lấy hàng	f	2026-06-03 08:47:08.858537+07	2026-06-03 08:50:27.509363+07	\N	1	\N
60f4f3cd8eaf452cb9bda77c4fcf56ab	AGV01	wf:312653cc-e6f2-4a8b-b4cf-1c9810ba2982	1	2	once	2026-06-03 09:15:00+07	\N	\N	\N	Lấy hàng	f	2026-06-03 09:14:47.978892+07	2026-06-03 09:15:28.117287+07	\N	1	\N
b8141fda84444417ae5d5560ed7b36e7	AGV01	wf:312653cc-e6f2-4a8b-b4cf-1c9810ba2982	1	1	once	2026-06-03 09:28:00+07	\N	\N	\N	Lấy hàng	f	2026-06-03 09:26:06.761359+07	2026-06-03 09:28:14.044435+07	\N	1	1779790224391
23e369b79fa04c399318fa22d6ada9ea	AGV01	wf:312653cc-e6f2-4a8b-b4cf-1c9810ba2982	1	1	once	2026-06-03 09:37:00+07	\N	\N	\N	Lấy hàng	f	2026-06-03 09:35:36.108284+07	2026-06-03 09:37:15.063882+07	\N	1	1779790224391
e36d12448d9d4dd5a545d7764870562c	AGV01	wf:312653cc-e6f2-4a8b-b4cf-1c9810ba2982	1	2	once	2026-06-03 09:56:00+07	\N	\N	\N	Lấy hàng	f	2026-06-03 09:54:30.991565+07	2026-06-03 09:56:15.624649+07	\N	1	1779790224391
f2061afc91ef4b6982cb7369bb116305	AGV01	wf:312653cc-e6f2-4a8b-b4cf-1c9810ba2982	1	2	once	2026-06-03 10:17:00+07	\N	\N	\N	Lấy hàng	f	2026-06-03 10:15:36.806138+07	2026-06-03 10:17:07.449847+07	\N	1	1779790224391
4d0e8139608a4fcb8789a76547651dcb	AGV02	wf:312653cc-e6f2-4a8b-b4cf-1c9810ba2982	1	2	once	2026-06-03 10:39:00+07	\N	\N	\N	Lấy hàng	f	2026-06-03 10:38:37.583261+07	2026-06-03 10:39:08.243304+07	\N	1	1779790224391
4139920c50f44e90af809e296ac8cd39	AGV02	wf:312653cc-e6f2-4a8b-b4cf-1c9810ba2982	4	2	once	2026-06-06 11:34:00+07	\N	\N	\N	Lấy hàng	f	2026-06-06 11:32:18.035606+07	2026-06-06 11:34:12.536385+07	\N	1	1779790224391
9acf3d07620d47cc80823b1929fa03eb	AGV01	wf:312653cc-e6f2-4a8b-b4cf-1c9810ba2982	2	2	once	2026-06-07 10:18:00+07	\N	\N	\N	Lấy hàng	f	2026-06-06 22:18:59.437925+07	2026-06-08 08:28:00.379264+07	\N	1	1779790224391
140c10f2f041489d9300880bc0d65979	AGV02	wf:312653cc-e6f2-4a8b-b4cf-1c9810ba2982	3	2	once	2026-06-07 10:18:00+07	\N	\N	\N		f	2026-06-06 22:19:25.784556+07	2026-06-08 08:28:00.535682+07	\N	1	1779790224391
\.


--
-- Data for Name: agv_task_executions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agv_task_executions (id, cmd_id, agv_id, command, dest_node, status, queued_at, started_at, completed_at, notes, session_id, session_label) FROM stdin;
1	4a5487e7	AGV01	go_to	41	failed	2026-05-22 14:19:45.627575+07	\N	\N	\N	\N	\N
2	62c2bc22	AGV01	go_to	225	failed	2026-05-22 14:33:18.362101+07	2026-05-22 14:33:18.362101+07	2026-05-22 14:33:18.401098+07	dispatch failed	\N	\N
3	b2162425	AGV01	go_to	225	failed	2026-05-22 14:36:18.877432+07	2026-05-22 14:36:18.877432+07	2026-05-22 14:36:18.886801+07	dispatch failed	\N	\N
4	3e891b1c	AGV01	go_to	225	running	2026-05-22 15:34:11.878708+07	\N	\N	\N	\N	\N
5	f9e73214	AGV01	stop	\N	queued	2026-05-22 15:38:35.945414+07	\N	\N	\N	\N	\N
6	ac2d7ad2	AGV01	stop	\N	queued	2026-05-22 15:38:45.624878+07	\N	\N	\N	\N	\N
7	584f06ce	AGV01	go_to	999	queued	2026-05-22 15:40:06.987747+07	\N	\N	\N	\N	\N
8	448f1f2e	AGV01	go_to	74	cancelled	2026-05-23 08:43:40.94338+07	2026-05-23 08:43:40.94338+07	2026-05-23 08:51:35.877672+07	force-cancelled by user	\N	\N
9	4684f034	AGV01	go_to	14	cancelled	2026-05-23 08:56:23.097271+07	2026-05-23 08:56:23.097271+07	2026-05-23 08:57:49.631494+07	force-cancelled by user	\N	\N
10	237fedbd	AGV01	go_to	41	cancelled	2026-05-23 09:03:10.41236+07	2026-05-23 09:03:10.41236+07	2026-05-23 09:11:52.578892+07	force-cancelled by user	\N	\N
11	6c342973	AGV01	go_to	14	cancelled	2026-05-23 09:16:46.811636+07	2026-05-23 09:16:46.811636+07	2026-05-23 09:17:38.759274+07	force-cancelled by user	\N	\N
12	eae47d4e	AGV01	go_to	14	cancelled	2026-05-23 09:18:18.043429+07	2026-05-23 09:18:18.043429+07	2026-05-23 09:20:32.352769+07	force-cancelled by user	\N	\N
13	737b3d5d	AGV01	go_to	14	running	2026-05-23 09:22:43.813404+07	\N	\N	\N	\N	\N
14	40290cbc	AGV01	go_to	14	cancelled	2026-05-23 09:26:36.514464+07	2026-05-23 09:26:36.514464+07	2026-05-23 09:29:12.697179+07	force-cancelled by user	\N	\N
15	f0da4a50	AGV01	go_to	14	running	2026-05-23 09:39:32.323183+07	\N	\N	\N	\N	\N
16	5308b08c	AGV01	go_to	14	running	2026-05-23 10:34:02.2627+07	\N	\N	\N	\N	\N
17	57359348	AGV01	go_to	14	completed	2026-05-23 10:45:35.489119+07	2026-05-23 10:45:35.489119+07	2026-05-23 10:46:11.154762+07	event:continue	\N	\N
18	6c514989	AGV01	go_to	14	completed	2026-05-23 11:30:01.01646+07	2026-05-23 11:30:01.01646+07	2026-05-23 11:30:29.434902+07	event:continue	\N	\N
19	77dd4d95	AGV01	go_to	999	cancelled	2026-05-25 13:29:32.064703+07	2026-05-25 13:29:32.064703+07	2026-05-25 13:30:19.797706+07	force-cancelled by user	\N	\N
20	5aee27a8	AGV01	go_to	999	cancelled	2026-05-25 13:30:30.290529+07	2026-05-25 13:30:30.290529+07	2026-05-25 13:30:42.75701+07	force-cancelled by user	\N	\N
21	2928937f	AGV01	go_to	999	completed	2026-05-25 15:59:46.428827+07	2026-05-25 15:59:46.428827+07	2026-05-25 16:00:23.730124+07	event:continue	\N	\N
22	bf15eee9	AGV01	go_to	14	completed	2026-05-25 16:10:56.07623+07	2026-05-25 16:10:56.07623+07	2026-05-25 16:11:35.969492+07	event:continue	\N	\N
38	124477b6	AGV01	go_charge	\N	failed	2026-05-26 09:48:07.619435+07	2026-05-26 09:49:14.481034+07	2026-05-26 09:49:14.508189+07	Không tìm thấy node charge trong map 1779430599645 | candidates=['CHARGE', 'Charge', 'ChargeStation', 'Trạm sạc', 'Sac', 'Sạc']	\N	\N
23	e3b92fd1	AGV01	go_to	999	completed	2026-05-25 16:10:56.10803+07	2026-05-25 16:11:35.969492+07	2026-05-25 16:12:01.227523+07	event:continue	\N	\N
24	e1a01187	AGV01	go_to	41	completed	2026-05-25 16:37:35.3889+07	2026-05-25 16:37:35.3889+07	2026-05-25 16:38:01.198507+07	lifecycle:delivering:confirmed	\N	\N
25	298019c4	AGV01	go_to	14	completed	2026-05-25 17:04:12.138962+07	2026-05-25 17:04:12.138962+07	2026-05-25 17:04:39.031002+07	lifecycle:delivering:confirmed	\N	\N
26	a1238af5	AGV01	go_to	41	completed	2026-05-25 17:04:12.17007+07	2026-05-25 17:04:39.032202+07	2026-05-25 17:05:07.80766+07	lifecycle:delivering:confirmed	\N	\N
27	8918b612	AGV01	go_to	16	completed	2026-05-26 08:26:06.748087+07	2026-05-26 08:26:06.748087+07	2026-05-26 08:26:18.602035+07	lifecycle:delivering:confirmed	\N	\N
28	ad970b9d	AGV01	go_to	41	completed	2026-05-26 08:26:06.790072+07	2026-05-26 08:26:18.650717+07	2026-05-26 08:26:58.024359+07	event:continue	\N	\N
29	eaa63f16	AGV01	go_to	16	cancelled	2026-05-26 08:49:54.098126+07	2026-05-26 08:49:54.098126+07	2026-05-26 08:51:53.051498+07	force-cancelled by user	\N	\N
30	1c5f7105	AGV01	go_to	999	cancelled	2026-05-26 08:49:54.292822+07	\N	2026-05-26 08:51:53.052505+07	cancelled by user	\N	\N
31	497de59f	AGV01	go_to	16	completed	2026-05-26 08:52:51.346372+07	2026-05-26 08:52:51.346372+07	2026-05-26 08:53:16.058268+07	event:continue	\N	\N
40	9d05d9fa	AGV01	go_charge	\N	cancelled	2026-05-26 09:56:00.495477+07	\N	2026-05-26 09:57:39.664108+07	cancelled by user	\N	\N
32	2ecb43eb	AGV01	go_to	41	completed	2026-05-26 08:52:51.361381+07	2026-05-26 08:53:16.060132+07	2026-05-26 08:53:38.363528+07	event:continue	\N	\N
33	3761b5cc	AGV01	go_to	14	completed	2026-05-26 09:19:54.613326+07	2026-05-26 09:19:54.613326+07	2026-05-26 09:20:19.984998+07	lifecycle:delivering:confirmed	\N	\N
39	b28f2f02	AGV01	go_to	74	cancelled	2026-05-26 09:56:00.120036+07	2026-05-26 09:56:00.120036+07	2026-05-26 09:57:42.483137+07	force-cancelled by user	\N	\N
34	fdf43945	AGV01	go_to	41	completed	2026-05-26 09:19:54.632303+07	2026-05-26 09:20:19.984998+07	2026-05-26 09:20:29.818275+07	lifecycle:delivering:confirmed	\N	\N
35	467f1f12	AGV01	go_charge	\N	failed	2026-05-26 09:19:54.646372+07	2026-05-26 09:20:29.85067+07	2026-05-26 09:20:29.932252+07	Không tìm thấy node charge trong map 1779430599645 | candidates=['CHARGE', 'Charge', 'ChargeStation', 'Trạm sạc', 'Sac', 'Sạc']	\N	\N
36	30601982	AGV01	go_to	41	completed	2026-05-26 09:48:07.550516+07	2026-05-26 09:48:07.550516+07	2026-05-26 09:48:34.250768+07	lifecycle:delivering:confirmed	\N	\N
49	1b898bca	AGV01	go_charge	\N	completed	2026-05-26 13:12:45.33742+07	2026-05-26 13:13:32.609843+07	2026-05-26 13:15:01.352683+07	lifecycle:picking:confirmed	\N	\N
37	cc021c65	AGV01	go_to	999	completed	2026-05-26 09:48:07.60589+07	2026-05-26 09:48:34.250768+07	2026-05-26 09:49:14.480034+07	event:continue	\N	\N
41	89355518	AGV01	go_to	16	completed	2026-05-26 10:27:10.294324+07	2026-05-26 10:27:10.294324+07	2026-05-26 10:27:20.020877+07	lifecycle:delivering:confirmed	\N	\N
42	7a8c32cc	AGV01	go_to	14	completed	2026-05-26 10:27:10.42155+07	2026-05-26 10:27:20.020877+07	2026-05-26 10:27:41.525307+07	lifecycle:delivering:confirmed	\N	\N
43	3dd4c1c4	AGV01	go_charge	\N	failed	2026-05-26 10:27:10.438894+07	2026-05-26 10:27:41.526302+07	2026-05-26 10:27:41.559047+07	Không tìm thấy node charge trong map 1779430599645 | candidates=['CHARGE', 'Charge', 'ChargeStation', 'Trạm sạc', 'Sac', 'Sạc']	\N	\N
44	ceab62fe	AGV01	go_to	14	completed	2026-05-26 13:10:58.602432+07	2026-05-26 13:10:58.602432+07	2026-05-26 13:11:11.067192+07	lifecycle:delivering:confirmed	\N	\N
50	45d339c6	AGV01	go_to	999	completed	2026-05-26 13:17:28.789885+07	2026-05-26 13:17:28.789885+07	2026-05-26 13:17:38.716241+07	lifecycle:delivering:confirmed	\N	\N
45	88772ecb	AGV01	go_to	14	completed	2026-05-26 13:10:58.624696+07	2026-05-26 13:11:11.068646+07	2026-05-26 13:11:40.264004+07	lifecycle:delivering:confirmed	\N	\N
46	0f017e18	AGV01	go_charge	\N	completed	2026-05-26 13:10:58.634131+07	2026-05-26 13:11:40.264004+07	2026-05-26 13:12:07.23557+07	lifecycle:picking:confirmed	\N	\N
47	1927b3bd	AGV01	go_to	41	completed	2026-05-26 13:12:45.215574+07	2026-05-26 13:12:45.215574+07	2026-05-26 13:13:09.880603+07	event:continue	\N	\N
54	a111fe7a	AGV01	go_to	999	completed	2026-05-26 13:19:43.410538+07	2026-05-26 13:20:00.096316+07	2026-05-26 13:20:39.491035+07	event:continue	\N	\N
48	45c4ab29	AGV01	go_to	41	completed	2026-05-26 13:12:45.322197+07	2026-05-26 13:13:09.881775+07	2026-05-26 13:13:32.607497+07	event:continue	\N	\N
58	79fee13d	AGV01	go_charge	\N	completed	2026-05-26 13:21:55.597538+07	2026-05-26 13:22:39.118701+07	2026-05-26 13:34:06.14573+07	lifecycle:picking:confirmed	\N	\N
51	193af5c1	AGV01	go_to	999	completed	2026-05-26 13:17:28.867806+07	2026-05-26 13:17:38.782252+07	2026-05-26 13:18:10.682306+07	lifecycle:delivering:confirmed	\N	\N
55	491a9329	AGV01	go_charge	\N	completed	2026-05-26 13:19:43.443098+07	2026-05-26 13:20:39.495033+07	2026-05-26 13:21:39.089467+07	lifecycle:picking:confirmed	\N	\N
52	c50877fd	AGV01	go_charge	\N	completed	2026-05-26 13:17:28.907811+07	2026-05-26 13:18:10.682306+07	2026-05-26 13:19:12.419296+07	lifecycle:picking:confirmed	\N	\N
57	c6666a2e	AGV01	go_to	999	completed	2026-05-26 13:21:55.580538+07	2026-05-26 13:22:06.626001+07	2026-05-26 13:22:39.117751+07	lifecycle:delivering:confirmed	\N	\N
53	1862df63	AGV01	go_to	999	completed	2026-05-26 13:19:43.342013+07	2026-05-26 13:19:43.342013+07	2026-05-26 13:20:00.094272+07	event:continue	\N	\N
56	8f3095a4	AGV01	go_to	999	completed	2026-05-26 13:21:55.208811+07	2026-05-26 13:21:55.208811+07	2026-05-26 13:22:06.626001+07	lifecycle:delivering:confirmed	\N	\N
61	7e066086	AGV01	go_charge	\N	completed	2026-05-26 13:52:27.350159+07	2026-05-26 13:53:12.929636+07	2026-05-26 14:04:26.715726+07	lifecycle:picking:confirmed	\N	\N
59	4fc2ef4d	AGV01	go_to	999	completed	2026-05-26 13:52:27.245703+07	2026-05-26 13:52:27.245703+07	2026-05-26 13:52:40.227108+07	lifecycle:delivering:confirmed	\N	\N
64	ecea6b78	AGV01	go_charge	\N	completed	2026-05-26 14:04:53.024168+07	2026-05-26 14:06:02.051798+07	2026-05-26 14:06:36.9069+07	lifecycle:picking:confirmed	\N	\N
60	1c0d7ff3	AGV01	go_to	999	completed	2026-05-26 13:52:27.321732+07	2026-05-26 13:52:40.227108+07	2026-05-26 13:53:12.929636+07	lifecycle:delivering:confirmed	\N	\N
62	6154979d	AGV01	go_to	999	completed	2026-05-26 14:04:52.853476+07	2026-05-26 14:04:52.853476+07	2026-05-26 14:05:07.509893+07	lifecycle:delivering:confirmed	\N	\N
65	87735110	AGV01	go_to	999	completed	2026-05-26 14:06:45.090753+07	2026-05-26 14:06:45.090753+07	2026-05-26 14:06:55.659928+07	lifecycle:delivering:confirmed	\N	\N
63	0b91dc40	AGV01	go_to	999	completed	2026-05-26 14:04:53.016959+07	2026-05-26 14:05:07.509893+07	2026-05-26 14:06:02.050796+07	lifecycle:delivering:confirmed	\N	\N
112	fcddbedb	AGV01	go_charge	\N	completed	2026-05-27 14:01:35.354804+07	2026-05-27 14:01:35.354804+07	2026-05-27 14:01:40.627979+07		\N	\N
66	9b8df27b	AGV01	go_to	999	completed	2026-05-26 14:06:45.100775+07	2026-05-26 14:06:55.698922+07	2026-05-26 14:07:20.59496+07	lifecycle:delivering:confirmed	\N	\N
100	170c6bca	AGV01	go_to	3	completed	2026-05-27 13:14:28.818963+07	2026-05-27 13:14:28.818963+07	2026-05-27 13:14:45.582953+07	lifecycle:delivering:confirmed	\N	\N
67	68222aeb	AGV01	go_charge	\N	completed	2026-05-26 14:06:45.114433+07	2026-05-26 14:07:20.59496+07	2026-05-26 14:07:54.522979+07	lifecycle:picking:confirmed	\N	\N
68	acc00bbd	AGV01	go_charge	\N	cancelled	2026-05-27 08:16:12.914691+07	2026-05-27 08:16:12.914691+07	2026-05-27 08:24:33.077362+07	force-cancelled by user	\N	\N
69	f431cc24	AGV01	go_charge	\N	cancelled	2026-05-27 08:25:05.752356+07	2026-05-27 08:25:05.752356+07	2026-05-27 08:37:02.450017+07	force-cancelled by user	\N	\N
70	515d5e79	AGV01	go_to	7	running	2026-05-27 09:18:01.10244+07	\N	\N	\N	\N	\N
71	66706ca9	AGV01	go_charge	\N	cancelled	2026-05-27 09:18:01.135232+07	\N	2026-05-27 09:18:10.300835+07	cancelled by user	\N	\N
72	92a8984f	AGV01	go_charge	\N	failed	2026-05-27 09:45:05.179949+07	2026-05-27 09:45:05.179949+07	2026-05-27 09:45:05.207263+07	column "lidar_off" does not exist	\N	\N
73	4f4557de	AGV01	go_charge	\N	failed	2026-05-27 09:45:14.00435+07	2026-05-27 09:45:14.00435+07	2026-05-27 09:45:14.122246+07	column "lidar_off" does not exist	\N	\N
74	0c38c9e8	AGV01	go_charge	\N	failed	2026-05-27 09:47:40.472905+07	2026-05-27 09:47:40.472905+07	2026-05-27 09:47:40.649088+07	column "lidar_off" does not exist	\N	\N
75	cd785aa8	AGV01	go_charge	\N	failed	2026-05-27 09:51:13.561951+07	2026-05-27 09:51:13.561951+07	2026-05-27 09:51:13.822355+07	column "lidar_off" does not exist	\N	\N
76	92ae9337	AGV01	go_charge	\N	completed	2026-05-27 09:59:36.749026+07	2026-05-27 09:59:36.749026+07	2026-05-27 09:59:47.655126+07	lifecycle:picking:confirmed	\N	\N
119	6eddcaa6	AGV01	go_charge	\N	cancelled	2026-05-27 14:10:02.01927+07	\N	2026-05-27 14:15:15.639354+07	cancelled by user	\N	\N
77	822e32a0	AGV01	go_to	13	completed	2026-05-27 09:59:37.014954+07	2026-05-27 09:59:47.655126+07	2026-05-27 10:02:01.274963+07	event:continue	\N	\N
78	4f1c6a4e	AGV01	go_charge	\N	cancelled	2026-05-27 10:23:33.407684+07	2026-05-27 10:23:33.407684+07	2026-05-27 10:32:35.317514+07	force-cancelled by user	\N	\N
79	ea56af1a	AGV01	go_charge	\N	failed	2026-05-27 10:55:25.993421+07	2026-05-27 10:55:25.993421+07	2026-05-27 10:55:26.348616+07	Không tìm được đường đi từ 0 -> 13	\N	\N
81	3b577f7a	AGV01	go_to	13	cancelled	2026-05-27 10:55:49.608448+07	\N	2026-05-27 10:57:28.206698+07	cancelled by user	\N	\N
80	17acdbfb	AGV01	go_charge	\N	cancelled	2026-05-27 10:55:49.58681+07	2026-05-27 10:55:49.58681+07	2026-05-27 10:57:31.597246+07	force-cancelled by user	\N	\N
82	689f24c5	AGV01	go_charge	\N	cancelled	2026-05-27 10:57:43.448486+07	2026-05-27 10:57:43.448486+07	2026-05-27 10:58:35.223281+07	force-cancelled by user	\N	\N
83	12899950	AGV01	go_to	13	cancelled	2026-05-27 10:57:43.456484+07	\N	2026-05-27 10:58:35.223281+07	cancelled by user	\N	\N
84	b6267b37	AGV01	go_to	18	cancelled	2026-05-27 10:59:09.68138+07	2026-05-27 10:59:09.68138+07	2026-05-27 11:01:43.528792+07	force-cancelled by user	\N	\N
85	7fbe6506	AGV01	go_to	17	cancelled	2026-05-27 10:59:09.953164+07	\N	2026-05-27 11:01:43.528792+07	cancelled by user	\N	\N
86	329d2e2f	AGV01	go_charge	\N	cancelled	2026-05-27 10:59:09.981978+07	\N	2026-05-27 11:01:43.528792+07	cancelled by user	\N	\N
88	293e4f51	AGV01	go_to	17	cancelled	2026-05-27 11:02:24.117771+07	\N	2026-05-27 11:12:34.025038+07	cancelled by user	\N	\N
87	39184582	AGV01	go_to	18	cancelled	2026-05-27 11:02:24.070071+07	2026-05-27 11:02:24.070071+07	2026-05-27 11:12:34.025038+07	force-cancelled by user	\N	\N
89	515076ef	AGV01	go_charge	\N	cancelled	2026-05-27 11:02:24.17317+07	\N	2026-05-27 11:12:34.025038+07	cancelled by user	\N	\N
90	ed7458fa	AGV01	go_to	19	failed	2026-05-27 11:25:10.487366+07	2026-05-27 11:25:10.487366+07	2026-05-27 11:25:10.732045+07	Không tìm được đường đi từ 0 -> 19	\N	\N
91	a6f3a653	AGV01	go_to	18	failed	2026-05-27 11:25:10.758416+07	2026-05-27 11:25:10.758416+07	2026-05-27 11:25:10.915493+07	Không tìm được đường đi từ 0 -> 18	\N	\N
92	cd766390	AGV01	go_to	18	failed	2026-05-27 11:40:52.912068+07	2026-05-27 11:40:52.912068+07	2026-05-27 11:40:52.945936+07	Không tìm được đường đi từ 0 -> 18	\N	\N
93	048d5d74	AGV01	go_to	17	failed	2026-05-27 11:40:52.957894+07	2026-05-27 11:40:52.957894+07	2026-05-27 11:40:53.230539+07	Không tìm được đường đi từ 0 -> 17	\N	\N
95	7cdceea2	AGV01	go_to	17	cancelled	2026-05-27 11:41:21.117277+07	\N	2026-05-27 11:43:08.923962+07	cancelled by user	\N	\N
96	13135f7b	AGV01	go_charge	\N	cancelled	2026-05-27 11:41:21.131268+07	\N	2026-05-27 11:43:08.923962+07	cancelled by user	\N	\N
94	7fab26e2	AGV01	go_to	18	cancelled	2026-05-27 11:41:20.947553+07	2026-05-27 11:41:20.947553+07	2026-05-27 11:43:08.923962+07	force-cancelled by user	\N	\N
97	d1ec403e	AGV01	go_to	19	cancelled	2026-05-27 11:44:50.895356+07	2026-05-27 11:44:50.895356+07	2026-05-27 11:54:10.37642+07	force-cancelled by user	\N	\N
99	8e7e0a81	AGV01	go_charge	\N	cancelled	2026-05-27 11:44:51.133359+07	\N	2026-05-27 11:54:10.378413+07	cancelled by user	\N	\N
98	9f4ef424	AGV01	go_to	18	cancelled	2026-05-27 11:44:51.11753+07	\N	2026-05-27 11:54:10.378413+07	cancelled by user	\N	\N
101	966b447c	AGV01	go_to	18	completed	2026-05-27 13:14:28.874533+07	2026-05-27 13:14:45.605948+07	2026-05-27 13:15:06.419541+07	lifecycle:delivering:confirmed	\N	\N
113	d1d1dc8e	AGV01	go_charge	\N	completed	2026-05-27 14:01:35.405792+07	2026-05-27 14:01:40.627979+07	2026-05-27 14:04:38.783545+07	lifecycle:picking:confirmed	\N	\N
102	f3f5b3b9	AGV01	go_charge	\N	completed	2026-05-27 13:14:28.895019+07	2026-05-27 13:15:06.420629+07	2026-05-27 13:15:14.686771+07	lifecycle:picking:confirmed	\N	\N
103	0ca53138	AGV01	go_to	13	cancelled	2026-05-27 13:15:06.446361+07	2026-05-27 13:15:14.686771+07	2026-05-27 13:15:46.697187+07	force-cancelled by user	\N	\N
104	11270256	AGV01	go_charge	\N	completed	2026-05-27 13:17:14.228024+07	2026-05-27 13:17:14.228024+07	2026-05-27 13:21:15.331932+07	lifecycle:picking:confirmed	\N	\N
105	42590617	AGV01	go_to	13	cancelled	2026-05-27 13:17:14.238104+07	2026-05-27 13:21:15.331932+07	2026-05-27 13:21:26.494783+07	force-cancelled by user	\N	\N
106	4ec51989	AGV01	go_charge	\N	completed	2026-05-27 13:32:00.17029+07	2026-05-27 13:32:00.17029+07	2026-05-27 13:32:13.046969+07	lifecycle:picking:confirmed	\N	\N
107	bd636d24	AGV01	go_to	13	running	2026-05-27 13:32:00.190888+07	2026-05-27 13:32:13.046969+07	\N		\N	\N
108	109c5f02	AGV01	go_charge	\N	completed	2026-05-27 13:32:45.737859+07	2026-05-27 13:32:45.737859+07	2026-05-27 13:32:53.949827+07	lifecycle:picking:confirmed	\N	\N
109	5fa3cb6d	AGV01	go_to	13	cancelled	2026-05-27 13:32:45.759952+07	2026-05-27 13:32:53.950825+07	2026-05-27 13:39:20.791698+07	force-cancelled by user	\N	\N
110	1e064b1d	AGV01	go_charge	\N	completed	2026-05-27 13:42:34.586885+07	2026-05-27 13:42:34.586885+07	2026-05-27 13:42:40.089786+07		\N	\N
111	118c8b60	AGV01	go_charge	\N	cancelled	2026-05-27 13:42:34.864719+07	2026-05-27 13:42:40.09076+07	2026-05-27 13:45:38.212095+07	force-cancelled by user	\N	\N
115	421a4818	AGV01	go_to	15	cancelled	2026-05-27 14:10:01.978336+07	\N	2026-05-27 14:15:15.639354+07	cancelled by user	\N	\N
114	51419a2c	AGV01	go_to	15	cancelled	2026-05-27 14:10:01.958466+07	2026-05-27 14:10:01.958466+07	2026-05-27 14:15:15.623339+07	force-cancelled by user	\N	\N
116	256e12e5	AGV01	go_to	18	cancelled	2026-05-27 14:10:01.992027+07	\N	2026-05-27 14:15:15.639354+07	cancelled by user	\N	\N
118	98e7c155	AGV01	go_to	16	cancelled	2026-05-27 14:10:02.01382+07	\N	2026-05-27 14:15:15.639354+07	cancelled by user	\N	\N
117	63974b69	AGV01	go_to	17	cancelled	2026-05-27 14:10:02.002551+07	\N	2026-05-27 14:15:15.639354+07	cancelled by user	\N	\N
120	4c1f4041	AGV01	go_to	15	running	2026-05-27 14:16:58.535222+07	\N	\N	\N	\N	\N
121	657380ec	AGV01	go_to	15	queued	2026-05-27 14:16:58.591737+07	\N	\N	\N	\N	\N
122	75a972e1	AGV01	go_to	18	queued	2026-05-27 14:16:58.60026+07	\N	\N	\N	\N	\N
123	6a7bb4d0	AGV01	go_to	16	queued	2026-05-27 14:16:58.618798+07	\N	\N	\N	\N	\N
124	321c514b	AGV01	go_to	17	queued	2026-05-27 14:16:58.623794+07	\N	\N	\N	\N	\N
125	2cbb68fa	AGV01	go_charge	\N	queued	2026-05-27 14:16:58.638267+07	\N	\N	\N	\N	\N
130	549046bd	AGV01	go_to	15	queued	2026-05-27 14:19:34.47407+07	\N	\N	\N	\N	\N
126	fe16f9dc	AGV01	go_to	18	completed	2026-05-27 14:19:34.394426+07	2026-05-27 14:19:34.394426+07	2026-05-27 14:20:08.012111+07	event:continue	\N	\N
128	af7da52f	AGV01	go_to	17	completed	2026-05-27 14:19:34.441614+07	2026-05-27 14:20:23.029631+07	2026-05-27 14:20:33.744138+07	event:continue	\N	\N
1242	e363c9ba	AGV01	go_charge	\N	running	2026-06-03 16:10:57.154277+07	2026-06-03 16:11:02.364297+07	\N		mpxuiinuyclvxwhhi1	A06
127	e91ce605	AGV01	go_to	18	completed	2026-05-27 14:19:34.428078+07	2026-05-27 14:20:08.014118+07	2026-05-27 14:20:23.028614+07	event:continue	\N	\N
129	f78a7a60	AGV01	go_to	16	running	2026-05-27 14:19:34.461053+07	2026-05-27 14:20:33.745132+07	\N		\N	\N
132	0c264a72	AGV01	go_to	16	queued	2026-05-27 14:20:51.535996+07	\N	\N	\N	\N	\N
131	14b00120	AGV01	go_charge	\N	queued	2026-05-27 14:19:34.482054+07	\N	\N	\N	\N	\N
133	30ce0ca0	AGV01	go_charge	\N	cancelled	2026-05-27 14:24:25.595372+07	2026-05-27 14:24:25.595372+07	2026-05-27 14:26:38.899006+07	force-cancelled by user	\N	\N
134	4ec01505	AGV01	go_charge	\N	running	2026-05-27 14:27:07.872968+07	\N	\N	\N	\N	\N
135	18c86e7a	AGV01	go_charge	\N	completed	2026-05-27 14:33:35.727767+07	2026-05-27 14:33:35.727767+07	2026-05-27 14:33:40.900048+07		\N	\N
173	30325f0c	AGV01	go_to	18	completed	2026-05-27 16:20:20.723544+07	2026-05-27 16:20:20.723544+07	2026-05-27 16:20:50.84068+07		\N	\N
136	41bd8978	AGV01	go_charge	\N	completed	2026-05-27 14:33:35.903819+07	2026-05-27 14:33:40.901994+07	2026-05-27 14:34:20.388908+07	charge_arrived	\N	\N
137	2825aa0d	AGV01	go_to	18	completed	2026-05-27 14:34:37.993138+07	2026-05-27 14:34:37.993138+07	2026-05-27 14:35:18.630788+07	event:continue	\N	\N
195	19a8ba4a	AGV01	go_to	10	cancelled	2026-05-27 22:06:43.935759+07	\N	2026-05-27 22:07:04.585402+07	cancelled by user	\N	\N
138	88b9b71e	AGV01	go_to	18	completed	2026-05-27 14:34:38.028091+07	2026-05-27 14:35:18.630788+07	2026-05-27 14:35:39.9411+07	event:continue	\N	\N
139	56a6c1ea	AGV01	go_to	17	completed	2026-05-27 14:34:38.042104+07	2026-05-27 14:35:39.942089+07	2026-05-27 14:35:49.437341+07	event:continue	\N	\N
174	9fcfbd64	AGV01	go_to	18	completed	2026-05-27 16:20:20.747505+07	2026-05-27 16:20:50.841674+07	2026-05-27 16:21:01.629504+07		\N	\N
140	5ef5b85a	AGV01	go_to	16	completed	2026-05-27 14:34:38.049009+07	2026-05-27 14:35:49.451349+07	2026-05-27 14:36:22.938598+07	event:continue	\N	\N
141	96061f21	AGV01	go_to	15	completed	2026-05-27 14:34:38.065831+07	2026-05-27 14:36:22.938598+07	2026-05-27 14:36:39.324573+07	event:continue	\N	\N
142	d908533e	AGV01	go_charge	\N	running	2026-05-27 14:34:38.071833+07	2026-05-27 14:36:39.325588+07	\N		\N	\N
144	67097d96	AGV01	go_to	19	cancelled	2026-05-27 15:11:56.076056+07	\N	2026-05-27 15:13:17.885931+07	cancelled by user	\N	\N
143	ce873f99	AGV01	go_to	19	cancelled	2026-05-27 15:11:56.047825+07	2026-05-27 15:11:56.047825+07	2026-05-27 15:13:17.885931+07	force-cancelled by user	\N	\N
145	11efbe11	AGV01	go_charge	\N	cancelled	2026-05-27 15:11:56.092756+07	\N	2026-05-27 15:13:17.885931+07	cancelled by user	\N	\N
146	daf4fe81	AGV01	go_to	18	running	2026-05-27 15:15:59.433353+07	\N	\N	\N	\N	\N
147	2776f29e	AGV01	go_to	18	queued	2026-05-27 15:15:59.446454+07	\N	\N	\N	\N	\N
148	3badd627	AGV01	go_to	15	queued	2026-05-27 15:15:59.46036+07	\N	\N	\N	\N	\N
149	ffe75a50	AGV01	go_to	17	queued	2026-05-27 15:15:59.469+07	\N	\N	\N	\N	\N
150	92396ce2	AGV01	go_to	16	queued	2026-05-27 15:15:59.48352+07	\N	\N	\N	\N	\N
151	fbd9e76e	AGV01	go_charge	\N	queued	2026-05-27 15:15:59.494362+07	\N	\N	\N	\N	\N
156	66c11a9e	AGV01	go_to	16	queued	2026-05-27 15:35:23.826756+07	\N	\N	\N	\N	\N
157	2b1ffaa7	AGV01	go_charge	\N	queued	2026-05-27 15:35:23.83502+07	\N	\N	\N	\N	\N
152	9fb19368	AGV01	go_to	18	completed	2026-05-27 15:35:23.615563+07	2026-05-27 15:35:23.615563+07	2026-05-27 15:35:57.317002+07	lifecycle:picking:confirmed	\N	\N
175	ea63485d	AGV01	go_to	15	completed	2026-05-27 16:20:20.759977+07	2026-05-27 16:21:01.630495+07	2026-05-27 16:21:06.865037+07		\N	\N
185	0ac3742a	AGV01	go_to	15	completed	2026-05-27 16:32:48.870207+07	2026-05-27 16:33:45.684683+07	2026-05-27 16:33:50.921782+07		\N	\N
153	f285659d	AGV01	go_to	18	completed	2026-05-27 15:35:23.791757+07	2026-05-27 15:35:57.329758+07	2026-05-27 15:36:25.150382+07	event:continue	\N	\N
154	2067275f	AGV01	go_to	15	completed	2026-05-27 15:35:23.81276+07	2026-05-27 15:36:25.151397+07	2026-05-27 15:36:30.423665+07		\N	\N
179	37e96cfe	AGV01	go_to	15	cancelled	2026-05-27 16:21:01.644158+07	2026-05-27 16:21:06.865037+07	2026-05-27 16:28:08.158143+07	force-cancelled by user	\N	\N
158	978687ee	AGV01	go_to	15	completed	2026-05-27 15:36:25.16983+07	2026-05-27 15:36:30.424873+07	2026-05-27 15:36:50.214891+07	event:continue	\N	\N
176	1c0d819b	AGV01	go_to	17	cancelled	2026-05-27 16:20:20.778342+07	\N	2026-05-27 16:28:08.158143+07	cancelled by user	\N	\N
155	ebbb264a	AGV01	go_to	17	completed	2026-05-27 15:35:23.821755+07	2026-05-27 15:36:50.222893+07	2026-05-27 15:39:10.264412+07	event:continue	\N	\N
159	f344a5c9	AGV01	go_to	17	running	2026-05-27 15:36:50.241515+07	2026-05-27 15:39:10.265421+07	\N		\N	\N
160	8987ac55	AGV01	go_to	17	queued	2026-05-27 15:39:10.284156+07	\N	\N	\N	\N	\N
161	d14b28c0	AGV01	go_to	18	running	2026-05-27 16:01:22.575688+07	\N	\N	\N	\N	\N
162	9029f645	AGV01	go_to	18	queued	2026-05-27 16:01:22.819412+07	\N	\N	\N	\N	\N
163	02c3ad43	AGV01	go_to	15	queued	2026-05-27 16:01:22.831596+07	\N	\N	\N	\N	\N
164	9a1502ab	AGV01	go_to	17	queued	2026-05-27 16:01:22.846854+07	\N	\N	\N	\N	\N
165	cbb7b4db	AGV01	go_to	16	queued	2026-05-27 16:01:22.859163+07	\N	\N	\N	\N	\N
166	c391ec4f	AGV01	go_charge	\N	queued	2026-05-27 16:01:22.872733+07	\N	\N	\N	\N	\N
167	84c63a14	AGV01	go_to	18	cancelled	2026-05-27 16:08:35.847309+07	2026-05-27 16:08:35.847309+07	2026-05-27 16:08:58.46587+07	force-cancelled by user	\N	\N
168	fb4843f4	AGV01	go_to	18	cancelled	2026-05-27 16:08:36.124653+07	\N	2026-05-27 16:08:58.46587+07	cancelled by user	\N	\N
169	1fc83140	AGV01	go_to	15	cancelled	2026-05-27 16:08:36.13378+07	\N	2026-05-27 16:08:58.46587+07	cancelled by user	\N	\N
170	d6cf8105	AGV01	go_to	17	cancelled	2026-05-27 16:08:36.145778+07	\N	2026-05-27 16:08:58.46587+07	cancelled by user	\N	\N
171	8d771952	AGV01	go_to	16	cancelled	2026-05-27 16:08:36.155786+07	\N	2026-05-27 16:08:58.46587+07	cancelled by user	\N	\N
172	5e428bc5	AGV01	go_charge	\N	cancelled	2026-05-27 16:08:36.166786+07	\N	2026-05-27 16:08:58.46587+07	cancelled by user	\N	\N
177	fa9e9c8b	AGV01	go_to	16	cancelled	2026-05-27 16:20:20.790255+07	\N	2026-05-27 16:28:08.158143+07	cancelled by user	\N	\N
178	6d3bceab	AGV01	go_charge	\N	cancelled	2026-05-27 16:20:20.7955+07	\N	2026-05-27 16:28:08.158143+07	cancelled by user	\N	\N
180	40c31123	AGV01	go_charge	\N	cancelled	2026-05-27 16:31:24.815112+07	2026-05-27 16:31:24.815112+07	2026-05-27 16:31:46.016244+07	force-cancelled by user	\N	\N
189	9e69a8bc	AGV01	go_to	15	running	2026-05-27 16:33:45.734907+07	2026-05-27 16:33:50.921782+07	\N		\N	\N
181	bd7cf783	AGV01	go_charge	\N	completed	2026-05-27 16:31:52.438471+07	2026-05-27 16:31:52.438471+07	2026-05-27 16:32:01.431299+07		\N	\N
182	8228b2dd	AGV01	go_charge	\N	completed	2026-05-27 16:31:52.477237+07	2026-05-27 16:32:01.432314+07	2026-05-27 16:32:34.75697+07	charge_arrived	\N	\N
186	c104bc84	AGV01	go_to	17	queued	2026-05-27 16:32:48.890205+07	\N	\N	\N	\N	\N
187	61072b8d	AGV01	go_to	16	queued	2026-05-27 16:32:48.900682+07	\N	\N	\N	\N	\N
188	2426bfc3	AGV01	go_charge	\N	queued	2026-05-27 16:32:48.90467+07	\N	\N	\N	\N	\N
183	6cc63e57	AGV01	go_to	18	completed	2026-05-27 16:32:48.807223+07	2026-05-27 16:32:48.807223+07	2026-05-27 16:33:32.551912+07	event:continue	\N	\N
196	a3f51863	AGV01	go_charge	\N	cancelled	2026-05-27 22:06:43.946115+07	\N	2026-05-27 22:07:04.585402+07	cancelled by user	\N	\N
184	d8fffd46	AGV01	go_to	18	completed	2026-05-27 16:32:48.841864+07	2026-05-27 16:33:32.552908+07	2026-05-27 16:33:45.683688+07	event:continue	\N	\N
190	094ee9ac	AGV01	go_charge	\N	cancelled	2026-05-27 16:46:02.943247+07	2026-05-27 16:46:02.943247+07	2026-05-27 16:46:17.078488+07	force-cancelled by user	\N	\N
191	ee303aec	AGV01	go_charge	\N	completed	2026-05-27 16:46:21.78293+07	2026-05-27 16:46:21.78293+07	2026-05-27 16:46:30.817823+07		\N	\N
192	2bf40ff8	AGV01	go_charge	\N	running	2026-05-27 16:46:21.805039+07	2026-05-27 16:46:30.835245+07	\N		\N	\N
193	47dd3395	AGV01	go_charge	13	queued	2026-05-27 16:47:05.966975+07	\N	\N	\N	\N	\N
194	bf9d5b45	AGV01	go_to	11	cancelled	2026-05-27 22:06:43.886217+07	2026-05-27 22:06:43.886217+07	2026-05-27 22:07:04.585402+07	force-cancelled by user	\N	\N
197	535c4b05	AGV01	go_charge	\N	completed	2026-05-28 09:53:40.170358+07	2026-05-28 09:53:40.170358+07	2026-05-28 09:54:14.079141+07	charge_arrived	\N	\N
198	fa0ef755	AGV01	go_to	18	completed	2026-05-28 09:55:35.47076+07	2026-05-28 09:55:35.47076+07	2026-05-28 09:56:09.708444+07	event:continue	\N	\N
200	534b795b	AGV01	go_to	17	completed	2026-05-28 09:55:35.669155+07	2026-05-28 09:56:22.951316+07	2026-05-28 09:56:31.989951+07	event:continue	\N	\N
201	e28579cb	AGV01	go_to	16	completed	2026-05-28 09:55:35.683169+07	2026-05-28 09:56:31.990951+07	2026-05-28 09:57:03.530106+07	event:continue	\N	\N
199	c2a9a830	AGV01	go_to	18	completed	2026-05-28 09:55:35.653858+07	2026-05-28 09:56:09.709426+07	2026-05-28 09:56:22.951316+07	event:continue	\N	\N
203	d55fcb0d	AGV01	go_charge	\N	completed	2026-05-28 09:55:35.709679+07	2026-05-28 09:57:11.750636+07	2026-05-28 09:58:15.307718+07	charge_arrived	\N	\N
202	6e0c2c31	AGV01	go_to	15	completed	2026-05-28 09:55:35.68916+07	2026-05-28 09:57:03.532104+07	2026-05-28 09:57:11.749636+07	event:continue	\N	\N
208	b6408ff4	AGV01	go_to	16	completed	2026-05-28 09:59:53.52606+07	2026-05-28 10:01:09.623869+07	2026-05-28 10:01:40.412884+07	lifecycle:picking:confirmed	\N	\N
2775	35e6c72b	AGV01	go_to	16	cancelled	2026-06-15 10:37:16.105555+07	2026-06-15 10:37:16.105539+07	2026-06-15 10:39:43.481187+07	force-cancelled by user	mqenv0dtxuepowp4my8	yield_siding
205	1381cdc8	AGV01	go_to	18	completed	2026-05-28 09:59:53.47568+07	2026-05-28 10:00:26.346253+07	2026-05-28 10:00:40.42911+07	event:continue	\N	\N
207	a24c2697	AGV01	go_to	17	completed	2026-05-28 09:59:53.513256+07	2026-05-28 10:00:58.052387+07	2026-05-28 10:01:09.622881+07	event:continue	\N	\N
204	f2664465	AGV01	go_to	18	completed	2026-05-28 09:59:53.399128+07	2026-05-28 09:59:53.399128+07	2026-05-28 10:00:26.346253+07	lifecycle:picking:confirmed	\N	\N
210	6f26b9fb	AGV01	go_to	15	completed	2026-05-28 10:00:40.448815+07	2026-05-28 10:00:45.652314+07	2026-05-28 10:00:58.051392+07	event:continue	\N	\N
209	cec95207	AGV01	go_charge	\N	completed	2026-05-28 09:59:53.537118+07	2026-05-28 10:01:40.412884+07	2026-05-28 10:02:48.350404+07	charge_arrived	\N	\N
1243	092848fb	AGV02	go_charge	\N	cancelled	2026-06-03 16:14:40.97698+07	2026-06-03 16:14:40.97698+07	2026-06-03 16:14:50.465313+07	force-cancelled by user	mpxuofr43js1p1yy3kb	Sạc Pin
1245	edd6ab11	AGV02	go_to	3	cancelled	2026-06-03 16:14:47.97006+07	\N	2026-06-03 16:14:50.466313+07	cancelled by user	mpxuofr43js1p1yy3kb	Sạc Pin
1244	4470f2a8	AGV02	go_charge	\N	cancelled	2026-06-03 16:14:41.172628+07	\N	2026-06-03 16:14:50.466313+07	cancelled by user	mpxuofr43js1p1yy3kb	Sạc Pin
1338	fe34a495	AGV02	go_charge	\N	cancelled	2026-06-03 16:58:13.785474+07	\N	2026-06-03 16:58:20.64866+07	cancelled by user	mpxw8fmzbmw3w7xmqh8	Sạc Pin
1337	4c8ce804	AGV02	go_charge	\N	cancelled	2026-06-03 16:58:13.567024+07	2026-06-03 16:58:13.567024+07	2026-06-03 16:58:20.643668+07	force-cancelled by user	mpxw8fmzbmw3w7xmqh8	Sạc Pin
1391	8b766897	AGV01	go_to	17	completed	2026-06-04 09:13:16.015758+07	2026-06-04 09:13:16.015758+07	2026-06-04 09:13:46.246072+07	lifecycle:picking:confirmed	mpyv2cf8hb9rpgnvzoh	A06
1398	dd5529d4	AGV01	go_charge	\N	cancelled	2026-06-04 09:14:12.32749+07	\N	2026-06-04 09:15:28.29502+07	cancelled by user	mpyv2cf8hb9rpgnvzoh	A06
1756	171064ec	AGV01	go_charge	\N	cancelled	2026-06-05 10:51:32.496691+07	2026-06-05 10:51:32.496691+07	2026-06-05 10:53:51.844966+07	force-cancelled by user	mq0e0ku9w630xl2sadj	Sạc Pin
1471	244b37b3	AGV02	go_charge	\N	completed	2026-06-04 10:35:36.48656+07	2026-06-04 10:35:42.486948+07	2026-06-04 10:36:26.914708+07	charge_arrived	mpyxx3m5abt1y3d25u6	A06
1482	7492b0c4	AGV01	go_charge	\N	completed	2026-06-04 10:48:08.570698+07	2026-06-04 10:48:08.570698+07	2026-06-04 10:48:54.837971+07	charge_arrived	\N	bounce_retry
1514	80c4ece1	AGV01	go_to	96	completed	2026-06-04 16:02:11.214742+07	2026-06-04 16:02:11.214742+07	2026-06-04 16:02:41.459479+07	event:continue	mpz9o7wi7bqkppnera9	A02
1581	11a43e4a	AGV02	go_charge	\N	completed	2026-06-05 09:14:56.487891+07	2026-06-05 09:14:56.487891+07	2026-06-05 09:15:25.032219+07	charge_arrived	\N	bounce_retry
1760	6f616595	AGV01	go_to	7	cancelled	2026-06-05 10:51:57.610771+07	\N	2026-06-05 10:53:51.845974+07	cancelled by user	mq0e0ku9w630xl2sadj	Sạc Pin
1583	04b27022	AGV01	go_to	69	completed	2026-06-05 09:15:24.706191+07	2026-06-05 09:15:47.369948+07	2026-06-05 09:15:56.873034+07		mq0akydcwef4z9vo7to	A06
1587	57c487bd	AGV01	go_to	64	cancelled	2026-06-05 09:16:14.937099+07	\N	2026-06-05 09:17:23.792086+07	cancelled by user	mq0akydcwef4z9vo7to	A06
1586	5173f539	AGV01	go_to	69	cancelled	2026-06-05 09:15:56.911457+07	\N	2026-06-05 09:17:23.792086+07	cancelled by user	mq0akydcwef4z9vo7to	A06
1584	1cd5a368	AGV01	go_charge	\N	cancelled	2026-06-05 09:15:24.711181+07	\N	2026-06-05 09:17:23.792086+07	cancelled by user	mq0akydcwef4z9vo7to	A06
1669	3abec8dd	AGV01	go_to	17	completed	2026-06-05 10:03:44.502941+07	2026-06-05 10:03:44.502941+07	2026-06-05 10:04:19.576219+07	lifecycle:picking:confirmed	mq0cb3vwc0vjnvjvhr	A06
1759	cf8c68a5	AGV01	go_to	6	cancelled	2026-06-05 10:51:50.436307+07	\N	2026-06-05 10:53:51.845974+07	cancelled by user	mq0e0ku9w630xl2sadj	Sạc Pin
1673	fcd8013a	AGV02	go_to	17	completed	2026-06-05 10:04:00.759041+07	2026-06-05 10:04:35.910453+07	2026-06-05 10:05:20.960628+07		mq0cbgazqxecysr5098	A06
1758	8969f222	AGV01	go_to	5	cancelled	2026-06-05 10:51:41.123108+07	\N	2026-06-05 10:53:51.845974+07	cancelled by user	mq0e0ku9w630xl2sadj	Sạc Pin
1674	3864d2fa	AGV02	go_charge	\N	completed	2026-06-05 10:04:00.802032+07	2026-06-05 10:05:55.191129+07	2026-06-05 10:06:36.435674+07	charge_arrived	mq0cbgazqxecysr5098	A06
1686	cec4d834	AGV01	go_to	64	cancelled	2026-06-05 10:08:58.475326+07	\N	2026-06-05 10:12:32.586055+07	cancelled by user	mq0cgi80t8c7ui3t0w9	A06
1687	fd506f4e	AGV01	go_to	10	cancelled	2026-06-05 10:09:05.43879+07	\N	2026-06-05 10:12:32.586055+07	cancelled by user	mq0cgi80t8c7ui3t0w9	A06
1684	6f054e37	AGV01	go_to	17	cancelled	2026-06-05 10:08:51.295618+07	\N	2026-06-05 10:12:32.586055+07	cancelled by user	mq0cgi80t8c7ui3t0w9	A06
1688	9f2955ae	AGV02	go_to	9	cancelled	2026-06-05 10:09:08.409093+07	\N	2026-06-05 10:12:38.107718+07	cancelled by user	mq0cg89nmgyfj66cb8k	A06
1685	4c9adafe	AGV02	go_to	4	cancelled	2026-06-05 10:08:51.454442+07	\N	2026-06-05 10:12:38.107718+07	cancelled by user	mq0cg89nmgyfj66cb8k	A06
1757	8b5bbeb4	AGV01	go_charge	\N	cancelled	2026-06-05 10:51:32.545179+07	\N	2026-06-05 10:53:51.845974+07	cancelled by user	mq0e0ku9w630xl2sadj	Sạc Pin
1742	bb8e3f33	AGV02	go_to	17	completed	2026-06-05 10:45:56.231842+07	2026-06-05 10:46:52.372855+07	2026-06-05 10:47:54.100667+07	lifecycle:picking:confirmed	mq0dtd64t4r1dn2ecug	A06
1751	033608a6	AGV02	go_to	17	completed	2026-06-05 10:49:36.31988+07	2026-06-05 10:50:19.330603+07	2026-06-05 10:55:01.97284+07	lifecycle:picking:confirmed	mq0dy35pib47yd4352g	A06
1743	72df1838	AGV02	go_charge	\N	completed	2026-06-05 10:45:56.257858+07	2026-06-05 10:47:54.101669+07	2026-06-05 10:48:08.841182+07		mq0dtd64t4r1dn2ecug	A06
1746	8f6d616f	AGV02	go_charge	\N	completed	2026-06-05 10:47:54.14492+07	2026-06-05 10:48:08.843207+07	2026-06-05 10:48:50.726336+07	charge_arrived	mq0dtd64t4r1dn2ecug	A06
1930	4bab3ca7	AGV02	go_charge	\N	completed	2026-06-05 14:05:01.995734+07	2026-06-05 14:05:01.995734+07	2026-06-05 14:05:02.011732+07	bounce_wait	mq0kxeslu5vox6lef1	Sạc Pin
1796	cee80003	AGV02	go_to	17	cancelled	2026-06-05 11:33:03.417627+07	2026-06-05 11:33:17.701634+07	2026-06-05 11:37:23.16681+07	force-cancelled by user	mq0fglvt3birpc9khno	A06
1802	788d0064	AGV02	go_to	19	cancelled	2026-06-05 11:33:38.150883+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1800	d93cad2e	AGV02	go_to	4	cancelled	2026-06-05 11:33:31.003942+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1803	163b8d1f	AGV01	go_to	6	cancelled	2026-06-05 11:33:38.630993+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1801	c348f5b0	AGV01	go_to	5	cancelled	2026-06-05 11:33:31.58198+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1799	39be5b3d	AGV01	go_charge	\N	cancelled	2026-06-05 11:33:17.732195+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1880	1683185a	AGV01	go_charge	\N	cancelled	2026-06-05 11:57:45.471371+07	\N	2026-06-05 13:16:03.02073+07	cancelled by user	mq0gbk66m0sxre51we	A06
1998	b4154446	AGV02	go_to	96	completed	2026-06-06 09:36:07.041571+07	2026-06-06 09:36:07.041571+07	2026-06-06 09:36:34.426396+07	lifecycle:picking:confirmed	mq1qrfmxrwxscfgmrf	A02
1949	07812d26	AGV02	go_to	69	completed	2026-06-05 15:40:21.113273+07	2026-06-05 15:40:51.143746+07	2026-06-05 15:41:06.712981+07		mq0obzmvod6h3vlol2	A06
1950	1bf7bd1a	AGV02	go_charge	\N	running	2026-06-05 15:40:21.138274+07	2026-06-05 15:41:46.504527+07	\N		mq0obzmvod6h3vlol2	A06
1969	f8f4edfa	AGV02	go_to	69	completed	2026-06-05 16:02:13.201506+07	2026-06-05 16:02:13.201506+07	2026-06-05 16:03:06.325477+07	lifecycle:picking:confirmed	mq0p443qs59j1txq17m	A02
1975	e1885660	AGV02	go_charge	\N	completed	2026-06-05 16:05:10.656152+07	2026-06-05 16:05:25.528811+07	2026-06-05 16:06:11.678836+07	charge_arrived	mq0p443qs59j1txq17m	A02
1974	3711eeed	AGV02	go_to	17	completed	2026-06-05 16:04:01.284547+07	2026-06-05 16:04:48.00157+07	2026-06-05 16:05:10.637112+07	lifecycle:picking:confirmed	mq0p443qs59j1txq17m	A02
1977	0cbb1a97	AGV02	go_to	69	completed	2026-06-05 16:07:04.377999+07	2026-06-05 16:07:31.934648+07	2026-06-05 16:07:47.284481+07		mq0pacqsb8k14wijidp	A05
1978	d2ea0da7	AGV02	go_to	96	completed	2026-06-05 16:07:04.394132+07	2026-06-05 16:08:26.3519+07	2026-06-05 16:09:10.130087+07	off_route	mq0pacqsb8k14wijidp	A05
1984	d8a2c503	AGV02	go_to	64	completed	2026-06-05 16:09:10.129088+07	2026-06-05 16:09:10.130087+07	2026-06-05 16:09:10.132102+07	already_at_dest	mq0pacqsb8k14wijidp	A05
1983	aebde003	AGV02	go_to	96	completed	2026-06-05 16:08:26.385435+07	2026-06-05 16:09:10.133091+07	2026-06-05 16:09:25.629059+07		mq0pacqsb8k14wijidp	A05
1979	8be5ce35	AGV02	go_to	17	completed	2026-06-05 16:07:04.403132+07	2026-06-05 16:09:42.262099+07	2026-06-05 16:11:43.519618+07	lifecycle:picking:confirmed	mq0pacqsb8k14wijidp	A05
1980	f8d76541	AGV02	go_to	16	completed	2026-06-05 16:07:04.4224+07	2026-06-05 16:12:04.2937+07	2026-06-05 16:12:19.142856+07		mq0pacqsb8k14wijidp	A05
1981	38ff8dfd	AGV02	go_charge	\N	completed	2026-06-05 16:07:04.441909+07	2026-06-05 16:12:49.43281+07	2026-06-05 16:13:47.812337+07	charge_arrived	mq0pacqsb8k14wijidp	A05
1992	987f15d8	AGV02	go_charge	14	cancelled	2026-06-05 16:57:30.810555+07	2026-06-05 16:57:30.834006+07	2026-06-05 16:57:34.446966+07	force-cancelled by user	mq0prigz87ferr8gtgn	A06
206	4f428457	AGV01	go_to	15	completed	2026-05-28 09:59:53.498532+07	2026-05-28 10:00:40.42911+07	2026-05-28 10:00:45.652314+07		\N	\N
251	307c821d	AGV01	go_charge	\N	cancelled	2026-05-28 11:46:06.373906+07	\N	2026-05-28 11:53:28.104066+07	cancelled by user	\N	\N
211	34aa02d2	AGV01	go_to	15	completed	2026-05-28 10:35:06.012067+07	2026-05-28 10:35:06.012067+07	2026-05-28 10:36:39.527511+07	lifecycle:picking:confirmed	\N	\N
236	8f9e5967	AGV01	go_charge	\N	completed	2026-05-28 11:38:20.257877+07	2026-05-28 11:38:20.257877+07	2026-05-28 11:38:29.243128+07		\N	\N
212	91ad5d30	AGV01	go_to	15	completed	2026-05-28 10:35:06.310985+07	2026-05-28 10:36:39.527511+07	2026-05-28 10:37:20.485784+07	lifecycle:picking:confirmed	\N	\N
213	af3b26fa	AGV01	go_to	17	completed	2026-05-28 10:35:06.321982+07	2026-05-28 10:37:20.486787+07	2026-05-28 10:37:53.988157+07	lifecycle:picking:confirmed	\N	\N
237	8a7a49ef	AGV01	go_charge	\N	completed	2026-05-28 11:38:20.277828+07	2026-05-28 11:38:29.24414+07	2026-05-28 11:39:02.679636+07	charge_arrived	\N	\N
214	6b2f1ed0	AGV01	go_to	18	completed	2026-05-28 10:35:06.333375+07	2026-05-28 10:37:53.988157+07	2026-05-28 10:37:59.419445+07		\N	\N
217	44a69911	AGV01	go_to	18	completed	2026-05-28 10:37:54.122451+07	2026-05-28 10:37:59.419445+07	2026-05-28 10:38:32.289882+07	event:continue	\N	\N
215	a732a52c	AGV01	go_to	16	completed	2026-05-28 10:35:06.346544+07	2026-05-28 10:38:32.289882+07	2026-05-28 10:39:06.700171+07	lifecycle:picking:confirmed	\N	\N
216	2653dbed	AGV01	go_charge	\N	completed	2026-05-28 10:35:06.359998+07	2026-05-28 10:39:06.717697+07	2026-05-28 10:40:14.661297+07	charge_arrived	\N	\N
218	f6d50c5c	AGV01	go_to	15	completed	2026-05-28 10:50:24.321367+07	2026-05-28 10:50:24.321367+07	2026-05-28 10:50:56.704145+07	lifecycle:picking:confirmed	\N	\N
219	2bbe5665	AGV01	go_to	15	completed	2026-05-28 10:50:24.493768+07	2026-05-28 10:50:56.704145+07	2026-05-28 10:51:46.058275+07	event:continue	\N	\N
220	16cdd52a	AGV01	go_to	17	completed	2026-05-28 10:50:24.512188+07	2026-05-28 10:51:46.059278+07	2026-05-28 10:52:22.632338+07	event:continue	\N	\N
221	78a0db76	AGV01	go_to	18	completed	2026-05-28 10:50:24.52511+07	2026-05-28 10:52:22.63435+07	2026-05-28 10:52:28.075562+07		\N	\N
238	e16b4745	AGV01	go_to	15	completed	2026-05-28 11:39:45.8278+07	2026-05-28 11:39:45.8278+07	2026-05-28 11:40:20.912953+07	lifecycle:picking:confirmed	\N	\N
224	eeeb8881	AGV01	go_to	18	completed	2026-05-28 10:52:22.710872+07	2026-05-28 10:52:28.077563+07	2026-05-28 10:52:42.247415+07	event:continue	\N	\N
249	b1df6f8b	AGV01	go_to	16	cancelled	2026-05-28 11:46:06.357902+07	\N	2026-05-28 11:53:28.104066+07	cancelled by user	\N	\N
222	1cd44bd0	AGV01	go_to	16	completed	2026-05-28 10:50:24.533241+07	2026-05-28 10:52:42.265427+07	2026-05-28 10:55:06.06658+07	event:continue	\N	\N
239	55a7c985	AGV01	go_to	15	completed	2026-05-28 11:39:46.121471+07	2026-05-28 11:40:20.912953+07	2026-05-28 11:41:03.717389+07	lifecycle:picking:confirmed	\N	\N
225	2e1e2307	AGV01	go_to	16	completed	2026-05-28 10:52:42.428804+07	2026-05-28 10:55:06.067584+07	2026-05-28 10:55:36.582715+07	event:continue	\N	\N
223	cb8e5cb7	AGV01	go_charge	\N	completed	2026-05-28 10:50:24.592915+07	2026-05-28 10:55:36.583707+07	2026-05-28 10:56:11.571703+07	charge_arrived	\N	\N
240	df26970a	AGV01	go_to	17	completed	2026-05-28 11:39:46.135804+07	2026-05-28 11:41:03.718412+07	2026-05-28 11:41:46.42223+07	lifecycle:picking:confirmed	\N	\N
226	95723e57	AGV01	go_to	15	completed	2026-05-28 11:15:01.545091+07	2026-05-28 11:15:01.545091+07	2026-05-28 11:15:34.720024+07	lifecycle:picking:confirmed	\N	\N
253	1a3d3878	AGV01	go_charge	\N	completed	2026-05-28 11:53:45.13632+07	2026-05-28 11:53:45.13632+07	2026-05-28 11:54:19.169786+07	charge_arrived	\N	\N
227	ae7152e3	AGV01	go_to	15	completed	2026-05-28 11:15:01.753729+07	2026-05-28 11:15:34.720024+07	2026-05-28 11:16:24.014246+07	lifecycle:picking:confirmed	\N	\N
228	a8adeace	AGV01	go_to	17	completed	2026-05-28 11:15:01.768286+07	2026-05-28 11:16:24.014246+07	2026-05-28 11:16:55.270166+07	lifecycle:picking:confirmed	\N	\N
229	aac5c1f6	AGV01	go_to	18	completed	2026-05-28 11:15:01.784248+07	2026-05-28 11:16:55.271164+07	2026-05-28 11:17:02.730668+07		\N	\N
241	4b19ce91	AGV01	go_to	18	completed	2026-05-28 11:39:46.149322+07	2026-05-28 11:41:46.442545+07	2026-05-28 11:41:51.963661+07		\N	\N
232	db6f7bbd	AGV01	go_to	18	completed	2026-05-28 11:16:55.304375+07	2026-05-28 11:17:02.738659+07	2026-05-28 11:17:12.029283+07	lifecycle:picking:confirmed	\N	\N
230	69063c65	AGV01	go_to	16	completed	2026-05-28 11:15:01.800961+07	2026-05-28 11:17:12.029283+07	2026-05-28 11:17:43.691589+07	lifecycle:picking:confirmed	\N	\N
244	894da093	AGV01	go_to	18	completed	2026-05-28 11:41:46.5634+07	2026-05-28 11:41:51.964662+07	2026-05-28 11:42:26.825137+07	lifecycle:picking:confirmed	\N	\N
231	b793421f	AGV01	go_charge	\N	completed	2026-05-28 11:15:01.812451+07	2026-05-28 11:17:43.708162+07	2026-05-28 11:17:48.802377+07		\N	\N
254	e9211d4d	AGV01	go_charge	\N	cancelled	2026-05-28 13:16:24.276701+07	2026-05-28 13:16:24.276701+07	2026-05-28 13:16:42.121647+07	force-cancelled by user	\N	\N
233	955550d1	AGV01	go_charge	\N	completed	2026-05-28 11:17:43.75572+07	2026-05-28 11:17:48.802377+07	2026-05-28 11:18:49.331086+07	event:continue	\N	\N
242	092ed798	AGV01	go_to	16	completed	2026-05-28 11:39:46.162696+07	2026-05-28 11:42:26.825137+07	2026-05-28 11:43:13.200071+07	lifecycle:picking:confirmed	\N	\N
234	5bab5309	AGV01	go_charge	13	cancelled	2026-05-28 11:18:02.003202+07	2026-05-28 11:18:49.331998+07	2026-05-28 11:27:01.34052+07	force-cancelled by user	\N	\N
235	b41f36e3	AGV01	go_charge	\N	cancelled	2026-05-28 11:37:51.429937+07	2026-05-28 11:37:51.429937+07	2026-05-28 11:38:13.127946+07	force-cancelled by user	\N	\N
255	d6c9c8c0	AGV01	go_charge	\N	cancelled	2026-05-28 13:16:49.824503+07	2026-05-28 13:16:49.824503+07	2026-05-28 13:17:05.021238+07	force-cancelled by user	\N	\N
243	8b5d0bb0	AGV01	go_charge	\N	completed	2026-05-28 11:39:46.175905+07	2026-05-28 11:43:13.200071+07	2026-05-28 11:43:18.362138+07		\N	\N
245	2c709c7d	AGV01	go_charge	\N	completed	2026-05-28 11:43:13.227013+07	2026-05-28 11:43:18.363144+07	2026-05-28 11:44:31.476827+07	charge_arrived	\N	\N
246	d4ccf2e3	AGV01	go_to	15	completed	2026-05-28 11:46:06.313354+07	2026-05-28 11:46:06.313354+07	2026-05-28 11:46:46.232169+07	lifecycle:picking:confirmed	\N	\N
256	9ed764c4	AGV01	go_charge	\N	running	2026-05-28 13:17:26.137218+07	\N	\N	\N	\N	\N
247	1eb3fc94	AGV01	go_to	15	completed	2026-05-28 11:46:06.330408+07	2026-05-28 11:46:46.232169+07	2026-05-28 11:47:43.041206+07	lifecycle:picking:confirmed	\N	\N
248	a45451e2	AGV01	go_to	18	completed	2026-05-28 11:46:06.345905+07	2026-05-28 11:47:43.041206+07	2026-05-28 11:47:48.980461+07		\N	\N
252	00ff1ecd	AGV01	go_to	18	cancelled	2026-05-28 11:47:43.060635+07	2026-05-28 11:47:48.981478+07	2026-05-28 11:53:28.091792+07	force-cancelled by user	\N	\N
250	c1e5e003	AGV01	go_to	17	cancelled	2026-05-28 11:46:06.361906+07	\N	2026-05-28 11:53:28.104066+07	cancelled by user	\N	\N
257	2ebb252d	AGV01	go_charge	\N	cancelled	2026-05-28 13:19:06.473522+07	2026-05-28 13:19:06.473522+07	2026-05-28 13:19:24.212238+07	force-cancelled by user	\N	\N
258	4b62d5bc	AGV01	go_charge	\N	cancelled	2026-05-28 13:19:06.668839+07	\N	2026-05-28 13:19:24.213269+07	cancelled by user	\N	\N
266	1484934b	AGV01	go_to	16	completed	2026-05-28 13:49:25.642935+07	2026-05-28 13:51:38.90664+07	2026-05-28 13:52:14.096944+07	lifecycle:picking:confirmed	\N	\N
259	36f99e07	AGV01	go_to	16	completed	2026-05-28 13:40:29.806662+07	2026-05-28 13:40:29.806662+07	2026-05-28 13:41:05.605756+07	lifecycle:picking:confirmed	\N	\N
264	094c5a8f	AGV01	go_to	15	completed	2026-05-28 13:49:25.604832+07	2026-05-28 13:50:18.594165+07	2026-05-28 13:51:05.657386+07	lifecycle:picking:confirmed	\N	\N
260	fc0a781e	AGV01	go_to	16	completed	2026-05-28 13:40:29.989696+07	2026-05-28 13:41:05.606761+07	2026-05-28 13:41:51.87256+07	lifecycle:picking:confirmed	\N	\N
261	f6f777f0	AGV01	go_charge	\N	completed	2026-05-28 13:40:30.007938+07	2026-05-28 13:41:51.87256+07	2026-05-28 13:41:56.948604+07		\N	\N
262	b7b803c5	AGV01	go_charge	\N	completed	2026-05-28 13:41:51.903581+07	2026-05-28 13:41:56.949657+07	2026-05-28 13:43:01.73675+07	charge_arrived	\N	\N
268	40e6e7d2	AGV01	go_charge	\N	completed	2026-05-28 13:49:25.670783+07	2026-05-28 13:52:49.058171+07	2026-05-28 13:53:31.34264+07	charge_arrived	\N	\N
263	589af37c	AGV01	go_to	15	completed	2026-05-28 13:49:25.563496+07	2026-05-28 13:49:25.563496+07	2026-05-28 13:50:18.594165+07	lifecycle:picking:confirmed	\N	\N
265	be7034af	AGV01	go_to	17	completed	2026-05-28 13:49:25.622603+07	2026-05-28 13:51:05.65838+07	2026-05-28 13:51:38.90664+07	lifecycle:picking:confirmed	\N	\N
271	e46d0078	AGV01	go_charge	\N	completed	2026-05-28 13:57:23.21096+07	2026-05-28 13:58:51.426711+07	2026-05-28 13:58:56.612244+07		\N	\N
267	cbcd9096	AGV01	go_to	18	completed	2026-05-28 13:49:25.660254+07	2026-05-28 13:52:14.097943+07	2026-05-28 13:52:49.058171+07	lifecycle:picking:confirmed	\N	\N
269	f49251e1	AGV01	go_to	16	completed	2026-05-28 13:57:23.157654+07	2026-05-28 13:57:23.157654+07	2026-05-28 13:58:00.909368+07	lifecycle:picking:confirmed	\N	\N
272	a12ae163	AGV01	go_to	15	completed	2026-05-28 13:58:03.130738+07	2026-05-28 14:00:09.43011+07	2026-05-28 14:00:52.641512+07	lifecycle:picking:confirmed	\N	\N
270	a5b24b25	AGV01	go_to	16	completed	2026-05-28 13:57:23.198965+07	2026-05-28 13:58:00.909368+07	2026-05-28 13:58:51.426711+07	lifecycle:picking:confirmed	\N	\N
274	c6052d8a	AGV01	go_charge	\N	completed	2026-05-28 13:58:51.449171+07	2026-05-28 13:58:56.614592+07	2026-05-28 14:00:09.429114+07	charge_arrived	\N	\N
275	5a24a15a	AGV01	go_to	15	completed	2026-05-28 14:00:09.456627+07	2026-05-28 14:00:52.641512+07	2026-05-28 14:03:28.048325+07	lifecycle:picking:confirmed	\N	\N
273	a453c895	AGV01	go_charge	\N	completed	2026-05-28 13:58:03.151242+07	2026-05-28 14:03:28.048325+07	2026-05-28 14:03:33.961337+07		\N	\N
276	04be673e	AGV01	go_charge	\N	completed	2026-05-28 14:03:28.077294+07	2026-05-28 14:03:33.964337+07	2026-05-28 14:08:23.866208+07	charge_arrived	\N	\N
301	3b3ba6f4	AGV01	go_charge	\N	completed	2026-05-28 14:32:54.713611+07	2026-05-28 14:34:42.534687+07	2026-05-28 14:35:25.517582+07	charge_arrived	\N	\N
277	06427db0	AGV01	go_to	11	completed	2026-05-28 14:11:13.337879+07	2026-05-28 14:11:13.337879+07	2026-05-28 14:11:41.012096+07	lifecycle:picking:confirmed	\N	\N
278	d56855a1	AGV01	go_to	15	completed	2026-05-28 14:11:13.565519+07	2026-05-28 14:11:41.013091+07	2026-05-28 14:12:30.177473+07	lifecycle:picking:confirmed	\N	\N
282	9da51300	AGV01	go_to	15	completed	2026-05-28 14:11:41.331238+07	2026-05-28 14:12:30.191972+07	2026-05-28 14:13:08.825388+07	lifecycle:picking:confirmed	\N	\N
279	ee0ba915	AGV01	go_to	16	completed	2026-05-28 14:11:13.58904+07	2026-05-28 14:13:08.825388+07	2026-05-28 14:13:20.459394+07	lifecycle:picking:confirmed	\N	\N
280	1085b98e	AGV01	go_to	18	completed	2026-05-28 14:11:13.636351+07	2026-05-28 14:13:20.459394+07	2026-05-28 14:13:25.630532+07		\N	\N
283	6d41ccdc	AGV01	go_to	18	completed	2026-05-28 14:13:20.482867+07	2026-05-28 14:13:25.631547+07	2026-05-28 14:15:50.091756+07	lifecycle:picking:confirmed	\N	\N
281	f6bce07a	AGV01	go_charge	\N	completed	2026-05-28 14:11:13.656405+07	2026-05-28 14:15:50.091756+07	2026-05-28 14:16:32.358178+07	charge_arrived	\N	\N
284	123bf757	AGV01	go_to	18	completed	2026-05-28 14:13:30.613325+07	2026-05-28 14:16:32.359166+07	2026-05-28 14:17:17.390395+07	lifecycle:picking:confirmed	\N	\N
330	4302878c	AGV01	go_charge	\N	cancelled	2026-05-29 11:38:45.539827+07	2026-05-29 11:38:45.539827+07	2026-05-29 11:39:05.99747+07	force-cancelled by user	mpqfmc5rnyz5qsbu17f	Sạc Pin
289	8b0ad661	AGV01	go_to	18	completed	2026-05-28 14:16:32.420637+07	2026-05-28 14:17:17.407397+07	2026-05-28 14:17:42.931632+07	lifecycle:picking:confirmed	\N	\N
306	2795b60f	AGV02	go_to	15	completed	2026-05-29 10:53:06.763717+07	2026-05-29 10:53:06.763717+07	2026-05-29 10:53:49.97832+07	event:continue	mpqdzmx302tukt9uj6zr	A04
322	d36e7ce4	AGV01	go_to	15	completed	2026-05-29 11:26:31.811199+07	2026-05-29 11:26:31.811199+07	2026-05-29 11:27:10.440428+07	lifecycle:picking:confirmed	mpqf6m0gzfvmxvsl88q	A04
285	5aebdf08	AGV01	go_to	16	completed	2026-05-28 14:13:30.628978+07	2026-05-28 14:17:42.932607+07	2026-05-28 14:18:13.799409+07	lifecycle:picking:confirmed	\N	\N
286	8f5bbce9	AGV01	go_to	15	completed	2026-05-28 14:13:30.642501+07	2026-05-28 14:18:13.799409+07	2026-05-28 14:18:18.929654+07		\N	\N
307	5dff350c	AGV02	go_to	15	completed	2026-05-29 10:53:06.781948+07	2026-05-29 10:53:49.97932+07	2026-05-29 10:54:29.400544+07	event:continue	mpqdzmx302tukt9uj6zr	A04
290	e748f313	AGV01	go_to	15	completed	2026-05-28 14:18:13.846556+07	2026-05-28 14:18:18.930604+07	2026-05-28 14:18:29.001577+07	lifecycle:picking:confirmed	\N	\N
308	2d19ed5d	AGV02	go_charge	\N	completed	2026-05-29 10:53:06.789198+07	2026-05-29 10:54:29.401535+07	2026-05-29 10:54:35.221068+07		mpqdzmx302tukt9uj6zr	A04
287	53846fa3	AGV01	go_to	17	completed	2026-05-28 14:13:30.653466+07	2026-05-28 14:18:29.002582+07	2026-05-28 14:19:40.392396+07	lifecycle:picking:confirmed	\N	\N
288	7e36c1fa	AGV01	go_charge	\N	completed	2026-05-28 14:13:30.670708+07	2026-05-28 14:19:40.392396+07	2026-05-28 14:19:45.714808+07		\N	\N
317	1a29e4c0	AGV02	go_to	15	completed	2026-05-29 11:07:55.557986+07	2026-05-29 11:07:55.557986+07	2026-05-29 11:08:38.857433+07	event:continue	mpqeiopvapg2tzw84m8	A04
291	4b7d6f99	AGV01	go_charge	\N	completed	2026-05-28 14:19:40.410706+07	2026-05-28 14:19:45.715799+07	2026-05-28 14:20:29.416381+07	charge_arrived	\N	\N
292	21599c05	AGV01	go_to	18	completed	2026-05-28 14:26:17.079827+07	2026-05-28 14:26:17.079827+07	2026-05-28 14:26:51.695478+07	lifecycle:picking:confirmed	\N	\N
309	6ca60b7b	AGV02	go_charge	\N	completed	2026-05-29 10:54:29.421993+07	2026-05-29 10:54:35.221068+07	2026-05-29 10:54:45.907282+07	event:continue	mpqdzmx302tukt9uj6zr	A04
293	ad72a09e	AGV01	go_to	18	completed	2026-05-28 14:26:17.30756+07	2026-05-28 14:26:51.695478+07	2026-05-28 14:27:08.363617+07	lifecycle:picking:confirmed	\N	\N
294	0781bdee	AGV01	go_to	16	completed	2026-05-28 14:26:17.317653+07	2026-05-28 14:27:08.363617+07	2026-05-28 14:27:46.277561+07	lifecycle:picking:confirmed	\N	\N
304	fe241e7b	AGV01	go_to	16	cancelled	2026-05-29 10:52:47.491891+07	\N	2026-05-29 10:59:33.80083+07	cancelled by user	mpqdz80p6lkel6txguy	A04
295	5c14e10b	AGV01	go_to	17	completed	2026-05-28 14:26:17.329186+07	2026-05-28 14:27:46.277561+07	2026-05-28 14:28:26.375158+07	lifecycle:picking:confirmed	\N	\N
303	6673efe3	AGV01	go_to	16	cancelled	2026-05-29 10:52:47.460387+07	2026-05-29 10:52:47.460387+07	2026-05-29 10:59:33.799418+07	force-cancelled by user	mpqdz80p6lkel6txguy	A04
305	75eec163	AGV01	go_charge	\N	cancelled	2026-05-29 10:52:47.50703+07	\N	2026-05-29 10:59:33.80083+07	cancelled by user	mpqdz80p6lkel6txguy	A04
296	5467ac54	AGV01	go_to	15	completed	2026-05-28 14:26:17.337679+07	2026-05-28 14:28:26.375158+07	2026-05-28 14:29:14.704773+07	lifecycle:picking:confirmed	\N	\N
297	5b9f3ead	AGV01	go_charge	\N	completed	2026-05-28 14:26:17.347805+07	2026-05-28 14:29:14.719187+07	2026-05-28 14:30:20.334367+07	charge_arrived	\N	\N
298	f0fd1c58	AGV01	go_to	15	completed	2026-05-28 14:32:54.628495+07	2026-05-28 14:32:54.628495+07	2026-05-28 14:33:28.411622+07	lifecycle:picking:confirmed	\N	\N
310	0f52b4ed	AGV02	go_charge	\N	cancelled	2026-05-29 10:57:36.292079+07	2026-05-29 10:57:36.292079+07	2026-05-29 11:00:22.057509+07	force-cancelled by user	mpqe5evzlgpijb6pho	Sạc Pin
299	e36228f2	AGV01	go_to	15	completed	2026-05-28 14:32:54.668178+07	2026-05-28 14:33:28.411622+07	2026-05-28 14:34:08.01085+07	lifecycle:picking:confirmed	\N	\N
300	bfb757de	AGV01	go_to	18	completed	2026-05-28 14:32:54.690927+07	2026-05-28 14:34:08.018395+07	2026-05-28 14:34:14.313286+07		\N	\N
318	25586923	AGV02	go_to	15	completed	2026-05-29 11:07:55.68813+07	2026-05-29 11:08:38.858422+07	2026-05-29 11:10:20.309198+07	event:continue	mpqeiopvapg2tzw84m8	A04
302	19844fcb	AGV01	go_to	18	completed	2026-05-28 14:34:08.330779+07	2026-05-28 14:34:14.318284+07	2026-05-28 14:34:42.534687+07	lifecycle:picking:confirmed	\N	\N
313	fcbbd9fd	AGV02	go_charge	\N	cancelled	2026-05-29 11:01:22.858888+07	2026-05-29 11:01:22.858888+07	2026-05-29 11:02:15.546866+07	force-cancelled by user	mpqea9pkbu8zgmvpxa	Sạc Pin
312	71d0d69d	AGV01	go_charge	\N	cancelled	2026-05-29 11:01:02.383176+07	\N	2026-05-29 11:02:20.848811+07	cancelled by user	mpqe9twinhxm8k9n9ve	Sạc Pin
311	439d8cb8	AGV01	go_charge	\N	cancelled	2026-05-29 11:01:02.372532+07	2026-05-29 11:01:02.372532+07	2026-05-29 11:02:20.84481+07	force-cancelled by user	mpqe9twinhxm8k9n9ve	Sạc Pin
314	302523a4	AGV01	go_to	16	completed	2026-05-29 11:07:34.108667+07	2026-05-29 11:07:34.108667+07	2026-05-29 11:08:25.066837+07	event:continue	mpqei85uvb6hoi5xcp	A04
323	bbffae27	AGV01	go_to	15	completed	2026-05-29 11:26:31.870188+07	2026-05-29 11:27:10.441431+07	2026-05-29 11:36:42.73758+07	lifecycle:picking:confirmed	mpqf6m0gzfvmxvsl88q	A04
319	9453ca18	AGV02	go_charge	\N	completed	2026-05-29 11:07:55.70803+07	2026-05-29 11:10:20.310223+07	2026-05-29 11:10:26.251997+07		mpqeiopvapg2tzw84m8	A04
325	4e8c6c43	AGV02	go_to	15	completed	2026-05-29 11:26:48.445394+07	2026-05-29 11:26:48.445394+07	2026-05-29 11:27:26.183484+07	lifecycle:picking:confirmed	mpqf6yuue9i9i98z2ma	A04
315	197bfd08	AGV01	go_to	16	completed	2026-05-29 11:07:34.140902+07	2026-05-29 11:08:25.066837+07	2026-05-29 11:10:27.8836+07	event:continue	mpqei85uvb6hoi5xcp	A04
316	49550e1e	AGV01	go_charge	\N	completed	2026-05-29 11:07:34.153568+07	2026-05-29 11:10:27.885609+07	2026-05-29 11:10:32.970638+07		mpqei85uvb6hoi5xcp	A04
327	b0f0b002	AGV02	go_charge	\N	cancelled	2026-05-29 11:26:48.510431+07	\N	2026-05-29 11:36:34.023453+07	cancelled by user	mpqf6yuue9i9i98z2ma	A04
320	64487789	AGV02	go_charge	\N	completed	2026-05-29 11:10:20.350419+07	2026-05-29 11:10:26.252995+07	2026-05-29 11:11:24.255069+07	charge_arrived	mpqeiopvapg2tzw84m8	A04
321	f02ec684	AGV01	go_charge	\N	cancelled	2026-05-29 11:10:27.921339+07	2026-05-29 11:10:32.971637+07	2026-05-29 11:20:20.328484+07	force-cancelled by user	mpqei85uvb6hoi5xcp	A04
326	189cb519	AGV02	go_to	15	cancelled	2026-05-29 11:26:48.483386+07	2026-05-29 11:27:26.183484+07	2026-05-29 11:36:34.022453+07	force-cancelled by user	mpqf6yuue9i9i98z2ma	A04
328	839446f3	AGV02	stop	\N	cancelled	2026-05-29 11:27:52.516443+07	\N	2026-05-29 11:36:34.023453+07	cancelled by user	\N	\N
329	9dbaf4c2	AGV01	go_charge	\N	completed	2026-05-29 11:36:42.784415+07	2026-05-29 11:37:11.721825+07	2026-05-29 11:38:12.75201+07	event:continue	mpqf6m0gzfvmxvsl88q	A04
324	78d67a4d	AGV01	go_charge	\N	completed	2026-05-29 11:26:31.891212+07	2026-05-29 11:36:42.738534+07	2026-05-29 11:37:11.71983+07		mpqf6m0gzfvmxvsl88q	A04
335	0f9aca72	AGV02	go_to	17	completed	2026-05-29 13:22:02.517462+07	2026-05-29 13:23:07.409663+07	2026-05-29 13:23:28.732519+07	lifecycle:picking:confirmed	mpqjb5hythvnq6d4kml	A04
336	82c282de	AGV02	go_charge	\N	completed	2026-05-29 13:22:02.577113+07	2026-05-29 13:23:28.732519+07	2026-05-29 13:23:34.118551+07		mpqjb5hythvnq6d4kml	A04
334	1f11b624	AGV02	go_to	17	completed	2026-05-29 13:22:02.168372+07	2026-05-29 13:22:02.168372+07	2026-05-29 13:23:07.402623+07	lifecycle:picking:confirmed	mpqjb5hythvnq6d4kml	A04
332	4aea7173	AGV01	go_to	16	completed	2026-05-29 13:21:47.18521+07	2026-05-29 13:22:24.446649+07	2026-05-29 13:23:11.967581+07	lifecycle:picking:confirmed	mpqjatjaqpzlv29khc	A04
3457	44874897	AGV01	go_to	96	cancelled	2026-06-19 12:03:45.071657+07	\N	2026-06-19 12:03:58.4136+07	cancelled by user	\N	\N
3468	88f99596	AGV01	go_to	18	queued	2026-06-21 10:04:22.092348+07	\N	\N	\N	\N	\N
331	b9e92003	AGV01	go_to	16	completed	2026-05-29 13:21:46.661519+07	2026-05-29 13:21:46.661519+07	2026-05-29 13:22:24.444632+07	lifecycle:picking:confirmed	mpqjatjaqpzlv29khc	A04
333	5b99bfd8	AGV01	go_charge	\N	completed	2026-05-29 13:21:47.263629+07	2026-05-29 13:23:11.968588+07	2026-05-29 13:23:17.245866+07		mpqjatjaqpzlv29khc	A04
361	24542132	AGV01	go_to	18	completed	2026-05-29 14:24:20.854269+07	2026-05-29 14:24:20.854269+07	2026-05-29 14:25:31.600758+07	lifecycle:picking:confirmed	mpqljab54iq6hkgoh9h	A04
338	21f7d419	AGV02	go_charge	\N	running	2026-05-29 13:23:28.75894+07	2026-05-29 13:23:34.11955+07	\N		mpqjb5hythvnq6d4kml	A04
337	63c13ed6	AGV01	go_charge	\N	completed	2026-05-29 13:23:12.102518+07	2026-05-29 13:23:17.24911+07	2026-05-29 13:24:21.661033+07	charge_arrived	mpqjatjaqpzlv29khc	A04
339	a02ecaef	AGV02	stop	\N	queued	2026-05-29 13:24:24.038312+07	\N	\N	\N	\N	\N
372	fae37f23	AGV02	go_charge	\N	completed	2026-05-29 14:30:19.82794+07	2026-05-29 14:31:35.773223+07	2026-05-29 14:31:41.074781+07		mpqlqz9pcoidcd44cul	A06
340	8c691d20	AGV01	go_to	17	completed	2026-05-29 13:47:57.426496+07	2026-05-29 13:47:57.426496+07	2026-05-29 13:48:41.129823+07	lifecycle:picking:confirmed	mpqk8hjs7iiq0f9r7in	A04
363	354baa6d	AGV01	go_charge	\N	cancelled	2026-05-29 14:24:21.078144+07	\N	2026-05-29 14:26:06.640848+07	cancelled by user	mpqljab54iq6hkgoh9h	A04
343	683607ad	AGV02	go_to	16	completed	2026-05-29 13:48:19.392254+07	2026-05-29 13:48:19.392254+07	2026-05-29 13:48:52.180089+07	lifecycle:picking:confirmed	mpqk8yiilqahbdkqki	A04
341	76a5575d	AGV01	go_to	17	completed	2026-05-29 13:47:57.49912+07	2026-05-29 13:48:41.129823+07	2026-05-29 13:49:15.348903+07	lifecycle:picking:confirmed	mpqk8hjs7iiq0f9r7in	A04
362	8fc3628b	AGV01	go_to	18	cancelled	2026-05-29 14:24:21.06158+07	2026-05-29 14:25:31.601741+07	2026-05-29 14:26:06.639834+07	force-cancelled by user	mpqljab54iq6hkgoh9h	A04
344	c46e90c3	AGV02	go_to	16	completed	2026-05-29 13:48:19.551621+07	2026-05-29 13:48:52.181109+07	2026-05-29 13:50:35.84606+07	lifecycle:picking:confirmed	mpqk8yiilqahbdkqki	A04
345	ba21493b	AGV02	go_charge	\N	completed	2026-05-29 13:48:19.572946+07	2026-05-29 13:50:35.846973+07	2026-05-29 13:50:40.911446+07		mpqk8yiilqahbdkqki	A04
364	6813180e	AGV01	go_charge	\N	cancelled	2026-05-29 14:26:16.66785+07	2026-05-29 14:26:16.66785+07	2026-05-29 14:26:41.56538+07	force-cancelled by user	mpqllro4pm1ebwmi8c	Sạc Pin
342	775d5ebc	AGV01	go_charge	\N	completed	2026-05-29 13:47:57.520129+07	2026-05-29 13:49:15.349908+07	2026-05-29 13:51:10.111509+07	charge_arrived	mpqk8hjs7iiq0f9r7in	A04
346	8a22a375	AGV02	go_charge	\N	completed	2026-05-29 13:50:35.877883+07	2026-05-29 13:50:40.911446+07	2026-05-29 13:51:45.500295+07	charge_arrived	mpqk8yiilqahbdkqki	A04
347	2ead8cd1	AGV01	go_to	17	completed	2026-05-29 14:04:57.317394+07	2026-05-29 14:04:57.317394+07	2026-05-29 14:05:35.9316+07	lifecycle:picking:confirmed	mpqkuci6c3phfzzgl1d	A04
351	45feed1a	AGV02	go_to	18	failed	2026-05-29 14:05:15.909396+07	2026-05-29 14:05:47.185097+07	2026-05-29 14:05:47.194099+07	AGV02: node đích 18 đang bị AGV01 chiếm hoặc heading đến — chờ AGV01 rời khỏi node trước	mpqkuqqbyw7097ljni	A04
350	8bc42456	AGV02	go_to	18	completed	2026-05-29 14:05:15.737456+07	2026-05-29 14:05:15.737456+07	2026-05-29 14:05:47.184102+07	lifecycle:picking:confirmed	mpqkuqqbyw7097ljni	A04
348	962c5e55	AGV01	go_to	17	completed	2026-05-29 14:04:57.384991+07	2026-05-29 14:05:35.954596+07	2026-05-29 14:06:26.333045+07	lifecycle:picking:confirmed	mpqkuci6c3phfzzgl1d	A04
365	dcf06ad4	AGV01	go_charge	\N	completed	2026-05-29 14:26:53.233999+07	2026-05-29 14:26:53.233999+07	2026-05-29 14:27:02.312475+07		mpqlmjvx4wop6fjgysh	Sạc Pin
349	28600d25	AGV01	go_charge	\N	completed	2026-05-29 14:04:57.407313+07	2026-05-29 14:06:26.333045+07	2026-05-29 14:06:37.7494+07		mpqkuci6c3phfzzgl1d	A04
373	802510c3	AGV02	go_charge	\N	running	2026-05-29 14:31:35.792981+07	2026-05-29 14:31:41.074781+07	\N		mpqlqz9pcoidcd44cul	A06
352	863dd59c	AGV02	go_charge	\N	cancelled	2026-05-29 14:05:15.946524+07	\N	2026-05-29 14:08:22.488216+07	cancelled by user	mpqkuqqbyw7097ljni	A04
354	0dc0dca9	AGV02	go_charge	\N	cancelled	2026-05-29 14:08:40.143739+07	2026-05-29 14:08:40.143739+07	2026-05-29 14:08:53.696562+07	force-cancelled by user	mpqkz4g688z7kmml0gt	Sạc Pin
355	56a5c9d0	AGV02	go_charge	\N	cancelled	2026-05-29 14:08:40.169761+07	\N	2026-05-29 14:08:53.765976+07	cancelled by user	mpqkz4g688z7kmml0gt	Sạc Pin
353	0085c208	AGV01	go_charge	\N	completed	2026-05-29 14:06:26.366636+07	2026-05-29 14:06:37.750915+07	2026-05-29 14:10:33.731998+07	charge_arrived	mpqkuci6c3phfzzgl1d	A04
358	0a6e1bf6	AGV01	go_charge	\N	queued	2026-05-29 14:11:29.22784+07	\N	\N	\N	mpql2qu7v3odmp0i61i	A04
356	92c278ab	AGV01	go_to	17	completed	2026-05-29 14:11:29.133509+07	2026-05-29 14:11:29.133509+07	2026-05-29 14:12:00.948072+07	event:continue	mpql2qu7v3odmp0i61i	A04
357	dbdfbb33	AGV01	go_to	17	running	2026-05-29 14:11:29.201262+07	2026-05-29 14:12:00.949093+07	\N		mpql2qu7v3odmp0i61i	A04
359	d0c2f1c5	AGV01	go_charge	\N	completed	2026-05-29 14:19:13.040354+07	2026-05-29 14:19:13.040354+07	2026-05-29 14:19:18.718555+07		mpqlcos1v4ey714lplo	Sạc Pin
366	debafeda	AGV01	go_charge	\N	completed	2026-05-29 14:26:53.255363+07	2026-05-29 14:27:02.313424+07	2026-05-29 14:27:29.044074+07	charge_arrived	mpqlmjvx4wop6fjgysh	Sạc Pin
360	c6aee11b	AGV01	go_charge	\N	completed	2026-05-29 14:19:13.377346+07	2026-05-29 14:19:18.720575+07	2026-05-29 14:20:02.656171+07	charge_arrived	mpqlcos1v4ey714lplo	Sạc Pin
367	fdc138c6	AGV01	go_to	17	completed	2026-05-29 14:29:36.977173+07	2026-05-29 14:29:36.977173+07	2026-05-29 14:30:24.251445+07	lifecycle:picking:confirmed	mpqlq287rfjv93n5xzt	A06
369	46a751a8	AGV01	go_charge	\N	completed	2026-05-29 14:29:37.015379+07	2026-05-29 14:31:38.129709+07	2026-05-29 14:31:49.736552+07		mpqlq287rfjv93n5xzt	A06
377	48ef9804	AGV01	go_to	15	completed	2026-05-29 15:41:53.787233+07	2026-05-29 15:41:53.787233+07	2026-05-29 15:42:22.868734+07	lifecycle:picking:confirmed	mpqob0j33fmnk39vsm4	A02
370	2e7a77c0	AGV02	go_to	16	completed	2026-05-29 14:30:19.793923+07	2026-05-29 14:30:19.793923+07	2026-05-29 14:30:52.338755+07	event:continue	mpqlqz9pcoidcd44cul	A06
371	470aae35	AGV02	go_to	16	completed	2026-05-29 14:30:19.80806+07	2026-05-29 14:30:52.339746+07	2026-05-29 14:31:35.772226+07	event:continue	mpqlqz9pcoidcd44cul	A06
388	6d11bb28	AGV02	go_to	18	completed	2026-05-29 15:44:28.89008+07	2026-05-29 15:44:28.89008+07	2026-05-29 15:45:03.819002+07	lifecycle:picking:confirmed	mpqoec7ptoje95gizjg	A02
368	fbec6d2c	AGV01	go_to	17	completed	2026-05-29 14:29:37.002134+07	2026-05-29 14:30:24.251445+07	2026-05-29 14:31:38.128696+07	event:continue	mpqlq287rfjv93n5xzt	A06
374	73d94895	AGV01	go_charge	\N	completed	2026-05-29 14:31:38.141009+07	2026-05-29 14:31:49.737566+07	2026-05-29 14:32:39.134619+07	charge_arrived	mpqlq287rfjv93n5xzt	A06
375	96f1c4d8	AGV02	go_charge	\N	completed	2026-05-29 14:37:19.390884+07	2026-05-29 14:37:19.390884+07	2026-05-29 14:37:27.879387+07		mpqlzz11z3r6rxfs4	Sạc Pin
381	c35a4a6d	AGV02	go_to	18	completed	2026-05-29 15:42:07.480248+07	2026-05-29 15:42:07.480248+07	2026-05-29 15:43:07.618069+07	event:continue	mpqobb3nofu27ooluz	A02
376	88ab51db	AGV02	go_charge	\N	completed	2026-05-29 14:37:19.43371+07	2026-05-29 14:37:27.880323+07	2026-05-29 14:37:55.08023+07	charge_arrived	mpqlzz11z3r6rxfs4	Sạc Pin
2776	62ec600b	AGV02	go_charge	\N	completed	2026-06-15 10:39:55.776489+07	2026-06-15 10:39:55.776474+07	2026-06-15 10:40:12.19449+07		mqeo054z6irogpaaxw	Sạc Pin
382	38fc3ba8	AGV02	go_to	18	cancelled	2026-05-29 15:42:07.556995+07	\N	2026-05-29 15:43:30.345468+07	cancelled by user	mpqobb3nofu27ooluz	A02
385	a8ed302d	AGV02	go_to	19	failed	2026-05-29 15:42:31.675895+07	2026-05-29 15:43:07.626871+07	2026-05-29 15:43:07.646073+07	AGV02: node đích 19 đang bị AGV01 chiếm hoặc heading đến — chờ AGV01 rời khỏi node trước	mpqobb3nofu27ooluz	A02
383	03d88900	AGV02	go_to	16	cancelled	2026-05-29 15:42:07.575779+07	\N	2026-05-29 15:43:30.345468+07	cancelled by user	mpqobb3nofu27ooluz	A02
384	a846df64	AGV02	go_charge	\N	cancelled	2026-05-29 15:42:07.591126+07	\N	2026-05-29 15:43:30.345468+07	cancelled by user	mpqobb3nofu27ooluz	A02
386	490c5403	AGV02	go_charge	\N	completed	2026-05-29 15:43:38.083723+07	2026-05-29 15:43:38.083723+07	2026-05-29 15:43:52.664991+07		mpqod90hatmigxclo9e	Sạc Pin
391	aa36c91c	AGV02	go_charge	\N	cancelled	2026-05-29 15:44:29.039862+07	\N	2026-05-29 15:51:31.386278+07	cancelled by user	mpqoec7ptoje95gizjg	A02
387	81e3ad25	AGV02	go_charge	\N	completed	2026-05-29 15:43:38.103778+07	2026-05-29 15:43:52.666987+07	2026-05-29 15:44:14.088912+07	charge_arrived	mpqod90hatmigxclo9e	Sạc Pin
390	d7876df4	AGV02	go_to	16	completed	2026-05-29 15:44:29.030459+07	2026-05-29 15:45:57.855975+07	2026-05-29 15:51:00.352784+07		mpqoec7ptoje95gizjg	A02
379	f474c07b	AGV01	go_to	17	completed	2026-05-29 15:41:54.064807+07	2026-05-29 15:44:44.55483+07	2026-05-29 15:45:19.421546+07	lifecycle:picking:confirmed	mpqob0j33fmnk39vsm4	A02
380	1582ff86	AGV01	go_charge	\N	completed	2026-05-29 15:41:54.079145+07	2026-05-29 15:45:19.421546+07	2026-05-29 15:50:20.389063+07		mpqob0j33fmnk39vsm4	A02
378	49381b70	AGV01	go_to	15	completed	2026-05-29 15:41:54.052327+07	2026-05-29 15:42:22.86972+07	2026-05-29 15:44:44.549978+07	lifecycle:picking:confirmed	mpqob0j33fmnk39vsm4	A02
389	f36f8614	AGV02	go_to	18	completed	2026-05-29 15:44:29.016336+07	2026-05-29 15:45:03.819002+07	2026-05-29 15:45:57.855975+07	lifecycle:picking:confirmed	mpqoec7ptoje95gizjg	A02
416	8d15cfc4	AGV02	go_charge	\N	completed	2026-05-29 16:12:21.772569+07	2026-05-29 16:13:39.036426+07	2026-05-29 16:13:45.031004+07		mpqpe6wpfy7qn9t3yaf	A06
392	a0271664	AGV01	go_charge	\N	completed	2026-05-29 15:45:19.659184+07	2026-05-29 15:50:20.391068+07	2026-05-29 15:50:32.812225+07	event:continue	mpqob0j33fmnk39vsm4	A02
425	0047b1c9	AGV02	go_charge	\N	completed	2026-05-29 16:15:31.623707+07	2026-05-29 16:18:30.136616+07	2026-05-29 16:18:35.509313+07		mpqpi9gzm2pa9kupcwc	A02
393	30a88173	AGV02	go_to	16	cancelled	2026-05-29 15:45:57.888108+07	2026-05-29 15:51:00.353768+07	2026-05-29 15:51:31.386278+07	force-cancelled by user	mpqoec7ptoje95gizjg	A02
394	0351416e	AGV02	go_to	16	cancelled	2026-05-29 15:51:00.371523+07	\N	2026-05-29 15:51:31.386278+07	cancelled by user	mpqoec7ptoje95gizjg	A02
395	c9ccad9c	AGV02	go_charge	\N	cancelled	2026-05-29 15:51:39.610634+07	2026-05-29 15:51:39.610634+07	2026-05-29 15:51:53.639813+07	force-cancelled by user	mpqonkk64sst7vab7tg	Sạc Pin
396	6f228032	AGV01	go_charge	\N	completed	2026-05-29 15:52:04.53755+07	2026-05-29 15:52:04.53755+07	2026-05-29 15:52:09.943775+07		mpqoo3sijh91yil4ay	Sạc Pin
413	9edfb84b	AGV01	go_charge	\N	completed	2026-05-29 16:10:56.56579+07	2026-05-29 16:13:07.022986+07	2026-05-29 16:14:02.997081+07	charge_arrived	mpqpcd469kzlp5wo48w	A02
398	40dd4cff	AGV02	go_charge	\N	cancelled	2026-05-29 15:52:19.391371+07	2026-05-29 15:52:19.391371+07	2026-05-29 15:52:31.396162+07	force-cancelled by user	mpqoof96vjjuymmnwpj	Sạc Pin
399	307f7bc9	AGV02	go_charge	\N	cancelled	2026-05-29 15:52:19.403845+07	\N	2026-05-29 15:52:31.399708+07	cancelled by user	mpqoof96vjjuymmnwpj	Sạc Pin
400	ffad0cf8	AGV02	go_charge	\N	cancelled	2026-05-29 15:52:46.122198+07	2026-05-29 15:52:46.122198+07	2026-05-29 15:52:57.317544+07	force-cancelled by user	mpqoozvsdoulcr28hwd	Sạc Pin
397	6dd0a326	AGV01	go_charge	\N	completed	2026-05-29 15:52:04.545538+07	2026-05-29 15:52:09.957774+07	2026-05-29 15:54:01.466235+07	charge_arrived	mpqoo3sijh91yil4ay	Sạc Pin
404	6524b11c	AGV01	go_charge	\N	queued	2026-05-29 15:59:02.745986+07	\N	\N	\N	mpqox2by7iju6stngcl	A02
407	bd55d54c	AGV02	go_to	16	queued	2026-05-29 15:59:20.878079+07	\N	\N	\N	mpqoxgfmbjhh9cojxko	A02
408	2f92d317	AGV02	go_charge	\N	queued	2026-05-29 15:59:20.895913+07	\N	\N	\N	mpqoxgfmbjhh9cojxko	A02
417	834bf3fb	AGV02	go_charge	\N	completed	2026-05-29 16:13:39.077914+07	2026-05-29 16:13:45.032028+07	2026-05-29 16:14:42.042378+07	charge_arrived	mpqpe6wpfy7qn9t3yaf	A06
401	bf8d93a0	AGV01	go_to	18	completed	2026-05-29 15:59:02.54842+07	2026-05-29 15:59:02.54842+07	2026-05-29 15:59:37.071822+07	lifecycle:picking:confirmed	mpqox2by7iju6stngcl	A02
402	b03cf957	AGV01	go_to	18	completed	2026-05-29 15:59:02.715887+07	2026-05-29 15:59:37.072829+07	2026-05-29 15:59:52.515446+07	lifecycle:picking:confirmed	mpqox2by7iju6stngcl	A02
405	4d2b8fbc	AGV02	go_to	17	completed	2026-05-29 15:59:20.823266+07	2026-05-29 15:59:20.823266+07	2026-05-29 15:59:55.059023+07	lifecycle:picking:confirmed	mpqoxgfmbjhh9cojxko	A02
406	11457fdd	AGV02	go_to	17	running	2026-05-29 15:59:20.853172+07	2026-05-29 15:59:55.060024+07	\N		mpqoxgfmbjhh9cojxko	A02
403	e259c644	AGV01	go_to	15	completed	2026-05-29 15:59:02.733464+07	2026-05-29 15:59:52.515446+07	2026-05-29 15:59:57.748459+07		mpqox2by7iju6stngcl	A02
409	a2402b3c	AGV01	go_to	15	running	2026-05-29 15:59:52.5331+07	2026-05-29 15:59:57.749458+07	\N		mpqox2by7iju6stngcl	A02
410	39f48456	AGV01	go_to	16	completed	2026-05-29 16:10:56.369079+07	2026-05-29 16:10:56.369079+07	2026-05-29 16:11:27.121079+07	lifecycle:picking:confirmed	mpqpcd469kzlp5wo48w	A02
411	07df4423	AGV01	go_to	16	completed	2026-05-29 16:10:56.539934+07	2026-05-29 16:11:27.122073+07	2026-05-29 16:12:28.531908+07	lifecycle:picking:confirmed	mpqpcd469kzlp5wo48w	A02
414	cf5f089c	AGV02	go_to	15	completed	2026-05-29 16:12:21.629032+07	2026-05-29 16:12:21.629032+07	2026-05-29 16:12:55.024218+07	lifecycle:picking:confirmed	mpqpe6wpfy7qn9t3yaf	A06
412	f9bae3ba	AGV01	go_to	17	completed	2026-05-29 16:10:56.553446+07	2026-05-29 16:12:28.531908+07	2026-05-29 16:13:07.022986+07	lifecycle:picking:confirmed	mpqpcd469kzlp5wo48w	A02
431	9166160c	AGV01	go_to	16	completed	2026-05-29 16:51:24.698458+07	2026-05-29 16:52:18.306496+07	2026-05-29 16:52:50.53806+07	event:continue	mpqqseibbwicp3rkqfu	A05
427	88f4fb45	AGV01	go_to	15	completed	2026-05-29 16:18:22.143689+07	2026-05-29 16:18:27.274531+07	2026-05-29 16:18:35.901043+07	lifecycle:picking:confirmed	mpqphxyvxv41k8j41ui	A02
415	0f146d43	AGV02	go_to	15	completed	2026-05-29 16:12:21.745306+07	2026-05-29 16:12:55.024218+07	2026-05-29 16:13:39.036426+07	lifecycle:picking:confirmed	mpqpe6wpfy7qn9t3yaf	A06
418	08d4a90c	AGV01	go_to	16	completed	2026-05-29 16:15:16.667273+07	2026-05-29 16:15:16.667273+07	2026-05-29 16:15:56.14446+07	lifecycle:picking:confirmed	mpqphxyvxv41k8j41ui	A02
435	fa43686c	AGV01	go_to	16	completed	2026-05-29 16:58:16.87256+07	2026-05-29 16:58:16.87256+07	2026-05-29 16:58:47.55999+07	lifecycle:picking:confirmed	mpqr18v7wnr09jy1l7r	A02
422	0d121d5f	AGV02	go_to	18	completed	2026-05-29 16:15:31.57633+07	2026-05-29 16:15:31.57633+07	2026-05-29 16:16:11.97069+07	lifecycle:picking:confirmed	mpqpi9gzm2pa9kupcwc	A02
428	8a760990	AGV02	go_charge	\N	completed	2026-05-29 16:18:30.157224+07	2026-05-29 16:18:35.51059+07	2026-05-29 16:19:19.576576+07	charge_arrived	mpqpi9gzm2pa9kupcwc	A02
423	8813c64f	AGV02	go_to	18	completed	2026-05-29 16:15:31.590045+07	2026-05-29 16:16:11.97069+07	2026-05-29 16:17:57.241203+07	event:continue	mpqpi9gzm2pa9kupcwc	A02
421	6597083e	AGV01	go_charge	\N	completed	2026-05-29 16:15:16.768564+07	2026-05-29 16:18:35.902041+07	2026-05-29 16:19:37.486166+07	charge_arrived	mpqphxyvxv41k8j41ui	A02
424	62552cd3	AGV02	go_to	17	completed	2026-05-29 16:15:31.606106+07	2026-05-29 16:17:57.2422+07	2026-05-29 16:18:09.325467+07	event:continue	mpqpi9gzm2pa9kupcwc	A02
419	0ac2b9ac	AGV01	go_to	16	completed	2026-05-29 16:15:16.726131+07	2026-05-29 16:15:56.145458+07	2026-05-29 16:18:22.121669+07	lifecycle:picking:confirmed	mpqphxyvxv41k8j41ui	A02
420	57e78c44	AGV01	go_to	15	completed	2026-05-29 16:15:16.743258+07	2026-05-29 16:18:22.121669+07	2026-05-29 16:18:27.273522+07		mpqphxyvxv41k8j41ui	A02
432	e9524f27	AGV01	go_to	17	completed	2026-05-29 16:51:24.71738+07	2026-05-29 16:52:50.539775+07	2026-05-29 16:53:23.588768+07	event:continue	mpqqseibbwicp3rkqfu	A05
426	6a9bcbdd	AGV02	go_to	17	completed	2026-05-29 16:17:57.26619+07	2026-05-29 16:18:09.327528+07	2026-05-29 16:18:30.135623+07	lifecycle:picking:confirmed	mpqpi9gzm2pa9kupcwc	A02
441	11c52b4b	AGV02	go_to	15	completed	2026-05-29 16:58:31.92829+07	2026-05-29 16:59:24.239513+07	2026-05-29 16:59:58.324198+07	lifecycle:picking:confirmed	mpqr1kfqw9ho9qwrem	A02
433	c1068717	AGV01	go_to	15	completed	2026-05-29 16:51:24.745787+07	2026-05-29 16:53:23.589432+07	2026-05-29 16:54:00.728294+07	event:continue	mpqqseibbwicp3rkqfu	A05
429	1d175621	AGV01	go_to	18	completed	2026-05-29 16:51:24.294929+07	2026-05-29 16:51:24.294929+07	2026-05-29 16:52:01.96138+07	event:continue	mpqqseibbwicp3rkqfu	A05
436	466f04d9	AGV01	go_to	16	completed	2026-05-29 16:58:17.056888+07	2026-05-29 16:58:47.55999+07	2026-05-29 16:59:37.17504+07	lifecycle:picking:confirmed	mpqr18v7wnr09jy1l7r	A02
430	46cbc61e	AGV01	go_to	18	completed	2026-05-29 16:51:24.666989+07	2026-05-29 16:52:01.966086+07	2026-05-29 16:52:18.301465+07	event:continue	mpqqseibbwicp3rkqfu	A05
439	4d14bca9	AGV02	go_to	18	completed	2026-05-29 16:58:31.870802+07	2026-05-29 16:58:31.870802+07	2026-05-29 16:59:05.75617+07	lifecycle:picking:confirmed	mpqr1kfqw9ho9qwrem	A02
434	193bb6c0	AGV01	go_charge	\N	completed	2026-05-29 16:51:24.75711+07	2026-05-29 16:54:00.729291+07	2026-05-29 16:55:02.971711+07	charge_arrived	mpqqseibbwicp3rkqfu	A05
440	a2891442	AGV02	go_to	18	completed	2026-05-29 16:58:31.907812+07	2026-05-29 16:59:05.75617+07	2026-05-29 16:59:24.238486+07	lifecycle:picking:confirmed	mpqr1kfqw9ho9qwrem	A02
437	2c034d2c	AGV01	go_to	17	completed	2026-05-29 16:58:17.084325+07	2026-05-29 16:59:37.176053+07	2026-05-29 17:00:13.8926+07	lifecycle:picking:confirmed	mpqr18v7wnr09jy1l7r	A02
442	755c97f3	AGV02	go_charge	\N	completed	2026-05-29 16:58:32.064506+07	2026-05-29 16:59:58.326359+07	2026-05-29 17:01:02.456906+07	charge_arrived	mpqr1kfqw9ho9qwrem	A02
438	4f01204e	AGV01	go_charge	\N	completed	2026-05-29 16:58:17.095814+07	2026-05-29 17:00:13.895619+07	2026-05-29 17:01:10.425315+07	charge_arrived	mpqr18v7wnr09jy1l7r	A02
443	62c62094	AGV01	go_to	18	running	2026-06-01 16:31:34.374914+07	\N	\N	\N	mpv0egd0ga0wlpfegvp	A06
444	a1e28496	AGV01	go_charge	\N	failed	2026-06-01 16:31:34.393552+07	2026-06-01 16:31:34.393552+07	2026-06-01 16:31:34.394916+07	AGV AGV01 chưa có mapCurrent/map_id	mpv0egd0ga0wlpfegvp	A06
1251	e3e07f72	AGV02	go_charge	\N	cancelled	2026-06-03 16:19:39.316667+07	\N	2026-06-03 16:21:57.48474+07	cancelled by user	mpxuutxk86oq9oswaon	A06
445	734e78df	AGV01	go_to	18	cancelled	2026-06-01 16:43:00.60284+07	2026-06-01 16:43:00.60284+07	2026-06-01 16:43:47.935069+07	force-cancelled by user	mpv0t5v38bumq5ivcj8	A06
1246	9f2d7322	AGV01	go_to	17	completed	2026-06-03 16:19:21.631232+07	2026-06-03 16:19:21.631232+07	2026-06-03 16:19:58.306413+07	event:continue	mpxuugbcgjbcews67cc	A06
1248	dec97258	AGV01	go_charge	\N	completed	2026-06-03 16:19:21.842902+07	2026-06-03 16:20:18.166537+07	2026-06-03 16:20:23.520326+07		mpxuugbcgjbcews67cc	A06
1676	b80be7f6	AGV01	go_charge	\N	completed	2026-06-05 10:04:45.551493+07	2026-06-05 10:05:03.747236+07	2026-06-05 10:05:52.869782+07	charge_arrived	mq0cb3vwc0vjnvjvhr	A06
1253	a39d6e60	AGV01	go_charge	\N	completed	2026-06-03 16:20:18.192534+07	2026-06-03 16:20:23.522332+07	2026-06-03 16:20:28.785472+07	event:continue	mpxuugbcgjbcews67cc	A06
1339	2cd07ea2	AGV01	go_to	17	completed	2026-06-03 16:59:32.045784+07	2026-06-03 16:59:32.045784+07	2026-06-03 17:00:10.014768+07	lifecycle:picking:confirmed	mpxwa4775qud0p0a4ti	A06
1343	8046c48a	AGV02	go_to	17	completed	2026-06-03 16:59:53.512375+07	2026-06-03 17:00:46.238559+07	2026-06-03 17:02:05.356764+07	event:continue	mpxwakka22kgbcl1625	A06
1344	3054c25f	AGV02	go_charge	\N	cancelled	2026-06-03 16:59:53.524368+07	\N	2026-06-03 17:05:43.843147+07	cancelled by user	mpxwakka22kgbcl1625	A06
1348	ff4923d4	AGV02	go_charge	\N	completed	2026-06-03 17:05:48.310408+07	2026-06-03 17:05:53.61011+07	2026-06-03 17:07:19.221031+07	charge_arrived	mpxwi6ik2qlnjvbtcug	Sạc Pin
1395	4d352ca2	AGV02	go_to	17	cancelled	2026-06-04 09:13:29.010018+07	2026-06-04 09:14:33.869485+07	2026-06-04 09:15:12.434188+07	force-cancelled by user	mpyv2m69n6wy18i7q9	A06
1397	11a3b680	AGV01	go_charge	\N	cancelled	2026-06-04 09:14:04.045953+07	2026-06-04 09:14:12.303942+07	2026-06-04 09:15:28.294018+07	force-cancelled by user	mpyv2cf8hb9rpgnvzoh	A06
1480	b28a28f6	AGV02	go_charge	\N	completed	2026-06-04 10:48:00.006282+07	2026-06-04 10:48:00.006282+07	2026-06-04 10:48:08.568698+07		mpyyg67odkz5je45k9f	Sạc Pin
1677	bde95334	AGV02	go_to	17	completed	2026-06-05 10:07:43.475612+07	2026-06-05 10:07:43.475612+07	2026-06-05 10:08:11.40765+07	lifecycle:picking:confirmed	mq0cg89nmgyfj66cb8k	A06
1518	e840cf62	AGV01	go_to	18	completed	2026-06-04 16:02:49.722313+07	2026-06-04 16:03:08.960289+07	2026-06-04 16:03:17.664877+07	event:continue	mpz9o7wi7bqkppnera9	A02
1598	fd1b0d31	AGV01	go_to	17	completed	2026-06-05 09:29:22.101891+07	2026-06-05 09:29:22.101891+07	2026-06-05 09:29:53.593924+07	lifecycle:picking:confirmed	mq0b2wj3pq6eblpnpmc	A06
1695	31c95621	AGV01	go_charge	\N	cancelled	2026-06-05 10:16:36.207272+07	2026-06-05 10:19:25.540101+07	2026-06-05 10:26:02.50978+07	force-cancelled by user	mq0crn9jk7p1lcajwht	A05
1600	86511911	AGV01	go_charge	\N	cancelled	2026-06-05 09:29:22.167153+07	\N	2026-06-05 09:32:12.846349+07	cancelled by user	mq0b2wj3pq6eblpnpmc	A06
1599	0fa42595	AGV01	go_to	17	cancelled	2026-06-05 09:29:22.149246+07	2026-06-05 09:29:53.593924+07	2026-06-05 09:32:12.845338+07	force-cancelled by user	mq0b2wj3pq6eblpnpmc	A06
1601	a6abbbb7	AGV02	go_to	17	completed	2026-06-05 09:29:41.61312+07	2026-06-05 09:29:41.61312+07	2026-06-05 09:32:31.85392+07	lifecycle:picking:confirmed	mq0b3bl5jmyn7319wsb	A06
1681	fa8a410d	AGV01	go_to	17	cancelled	2026-06-05 10:07:56.415852+07	2026-06-05 10:08:38.631347+07	2026-06-05 10:12:32.586055+07	force-cancelled by user	mq0cgi80t8c7ui3t0w9	A06
1606	7f945094	AGV02	go_to	9	cancelled	2026-06-05 09:33:08.740286+07	\N	2026-06-05 09:35:00.020229+07	cancelled by user	mq0b3bl5jmyn7319wsb	A06
1608	e1f07895	AGV02	go_to	9	cancelled	2026-06-05 09:33:25.052969+07	\N	2026-06-05 09:35:00.020229+07	cancelled by user	mq0b3bl5jmyn7319wsb	A06
1607	41ff3a95	AGV02	go_to	64	cancelled	2026-06-05 09:33:18.012994+07	\N	2026-06-05 09:35:00.020229+07	cancelled by user	mq0b3bl5jmyn7319wsb	A06
1603	e7fb8cef	AGV02	go_charge	\N	cancelled	2026-06-05 09:29:41.644507+07	\N	2026-06-05 09:35:00.020229+07	cancelled by user	mq0b3bl5jmyn7319wsb	A06
1605	52d7ff61	AGV02	go_to	64	cancelled	2026-06-05 09:32:59.455765+07	\N	2026-06-05 09:35:00.020229+07	cancelled by user	mq0b3bl5jmyn7319wsb	A06
1604	d12eb273	AGV02	go_to	17	cancelled	2026-06-05 09:32:50.209656+07	\N	2026-06-05 09:35:00.020229+07	cancelled by user	mq0b3bl5jmyn7319wsb	A06
1602	bf051a2e	AGV02	go_to	17	cancelled	2026-06-05 09:29:41.628487+07	2026-06-05 09:32:31.865044+07	2026-06-05 09:35:02.222802+07	force-cancelled by user	mq0b3bl5jmyn7319wsb	A06
1682	d74a1449	AGV01	go_charge	\N	cancelled	2026-06-05 10:07:56.444024+07	\N	2026-06-05 10:12:32.586055+07	cancelled by user	mq0cgi80t8c7ui3t0w9	A06
1672	f07118e0	AGV02	go_to	17	completed	2026-06-05 10:04:00.592082+07	2026-06-05 10:04:00.592082+07	2026-06-05 10:04:35.910453+07	lifecycle:picking:confirmed	mq0cbgazqxecysr5098	A06
1670	d93f6936	AGV01	go_to	17	completed	2026-06-05 10:03:44.814572+07	2026-06-05 10:04:19.584762+07	2026-06-05 10:04:45.393016+07	lifecycle:picking:confirmed	mq0cb3vwc0vjnvjvhr	A06
1671	b51c7e7c	AGV01	go_charge	\N	completed	2026-06-05 10:03:44.834046+07	2026-06-05 10:04:45.393016+07	2026-06-05 10:05:03.744236+07		mq0cb3vwc0vjnvjvhr	A06
1708	da877748	AGV01	go_to	8	cancelled	2026-06-05 10:20:21.398902+07	\N	2026-06-05 10:26:02.510782+07	cancelled by user	mq0crn9jk7p1lcajwht	A05
1707	7093576f	AGV01	go_to	19	cancelled	2026-06-05 10:20:14.233304+07	\N	2026-06-05 10:26:02.510782+07	cancelled by user	mq0crn9jk7p1lcajwht	A05
1691	c1f29d65	AGV01	go_to	18	completed	2026-06-05 10:16:36.146723+07	2026-06-05 10:17:05.236248+07	2026-06-05 10:17:19.145526+07	lifecycle:picking:confirmed	mq0crn9jk7p1lcajwht	A05
1706	51cd2077	AGV01	go_to	8	cancelled	2026-06-05 10:20:07.043078+07	\N	2026-06-05 10:26:02.510782+07	cancelled by user	mq0crn9jk7p1lcajwht	A05
1692	815e09e8	AGV01	go_to	17	completed	2026-06-05 10:16:36.165248+07	2026-06-05 10:17:19.148569+07	2026-06-05 10:17:34.10429+07	lifecycle:picking:confirmed	mq0crn9jk7p1lcajwht	A05
1705	b0d99fec	AGV01	go_to	19	cancelled	2026-06-05 10:20:00.09998+07	\N	2026-06-05 10:26:02.510782+07	cancelled by user	mq0crn9jk7p1lcajwht	A05
1704	d13d3f31	AGV01	go_to	8	cancelled	2026-06-05 10:19:50.562232+07	\N	2026-06-05 10:26:02.510782+07	cancelled by user	mq0crn9jk7p1lcajwht	A05
1698	83215f0e	AGV02	go_to	9	completed	2026-06-05 10:18:07.380203+07	2026-06-05 10:18:43.781166+07	2026-06-05 10:18:57.185068+07	lifecycle:picking:confirmed	mq0ctlkpihg5smkt3yo	A06
1693	45545266	AGV01	go_to	16	completed	2026-06-05 10:16:36.179251+07	2026-06-05 10:17:34.10429+07	2026-06-05 10:19:12.087477+07	lifecycle:picking:confirmed	mq0crn9jk7p1lcajwht	A05
1703	3d5306a6	AGV01	go_to	19	cancelled	2026-06-05 10:19:43.501605+07	\N	2026-06-05 10:26:02.510782+07	cancelled by user	mq0crn9jk7p1lcajwht	A05
1694	4ea5f173	AGV01	go_to	15	completed	2026-06-05 10:16:36.190255+07	2026-06-05 10:19:12.087477+07	2026-06-05 10:19:25.539089+07	lifecycle:picking:confirmed	mq0crn9jk7p1lcajwht	A05
1701	f6e83da0	AGV01	go_charge	\N	cancelled	2026-06-05 10:19:25.583826+07	\N	2026-06-05 10:26:02.510782+07	cancelled by user	mq0crn9jk7p1lcajwht	A05
1702	7995a95e	AGV01	go_to	8	cancelled	2026-06-05 10:19:36.358852+07	\N	2026-06-05 10:26:02.510782+07	cancelled by user	mq0crn9jk7p1lcajwht	A05
1709	22665dac	AGV01	go_to	19	cancelled	2026-06-05 10:20:30.6627+07	\N	2026-06-05 10:26:02.510782+07	cancelled by user	mq0crn9jk7p1lcajwht	A05
1699	d230e9d5	AGV02	go_charge	\N	cancelled	2026-06-05 10:18:07.394206+07	\N	2026-06-05 10:29:52.853128+07	cancelled by user	mq0ctlkpihg5smkt3yo	A06
2778	b260888a	AGV01	go_charge	\N	cancelled	2026-06-15 10:40:06.973212+07	2026-06-15 10:40:06.9732+07	2026-06-15 10:40:42.580713+07	force-cancelled by user	mqeo0ds2bsikhioyrw8	Sạc Pin
2779	96e89625	AGV01	go_charge	\N	cancelled	2026-06-15 10:40:12.198404+07	\N	2026-06-15 10:40:42.581182+07	cancelled by user	mqenv0dtxuepowp4my8	yield_resume
2781	681298ac	AGV01	go_charge	\N	completed	2026-06-15 10:40:49.493462+07	2026-06-15 10:41:04.383213+07	2026-06-15 10:41:53.93667+07	charge_arrived	mqeo1akkpqmnezqzof	Sạc Pin
2854	f1ea28ad	AGV02	go_to	19	completed	2026-06-15 11:55:06.991626+07	2026-06-15 11:55:26.305742+07	2026-06-15 11:56:23.206204+07	lifecycle:picking:confirmed	mqeqohediemmfo77i	A06
2940	7c96de22	AGV02	go_to	16	completed	2026-06-16 09:27:07.826466+07	2026-06-16 09:27:07.82646+07	2026-06-16 09:27:43.242938+07	event:continue	mqg0rsqmxxb3ku08rpf	dest_retry
2933	9accbc72	AGV02	go_to	19	completed	2026-06-16 09:25:07.658047+07	2026-06-16 09:25:07.658041+07	2026-06-16 09:25:38.310765+07		mqg0rsqmxxb3ku08rpf	A06
2934	ae4946e4	AGV02	go_to	19	completed	2026-06-16 09:25:07.666252+07	2026-06-16 09:25:38.312547+07	2026-06-16 09:26:03.29844+07	lifecycle:picking:confirmed	mqg0rsqmxxb3ku08rpf	A06
2932	b3836267	AGV01	go_charge	\N	completed	2026-06-16 09:24:55.460259+07	2026-06-16 09:26:50.925493+07	2026-06-16 09:27:07.824595+07		mqg0rjaf0o6iev2mwmpr	A06
2951	7ff18b51	AGV01	go_charge	\N	completed	2026-06-16 09:32:32.454897+07	2026-06-16 09:33:35.621566+07	2026-06-16 09:34:37.834055+07	charge_arrived	mqg0wuo8uy0gmf4ojt	A02
446	e4e86ed3	AGV01	go_to	18	cancelled	2026-06-01 16:43:00.640921+07	\N	2026-06-01 16:43:47.937058+07	cancelled by user	mpv0t5v38bumq5ivcj8	A06
1247	e5a61a6d	AGV01	go_to	17	completed	2026-06-03 16:19:21.827697+07	2026-06-03 16:19:58.306413+07	2026-06-03 16:20:18.164643+07	event:continue	mpxuugbcgjbcews67cc	A06
1252	8e567cf4	AGV02	go_to	17	cancelled	2026-06-03 16:20:14.956091+07	\N	2026-06-03 16:21:57.48474+07	cancelled by user	mpxuutxk86oq9oswaon	A06
1250	927bbdf0	AGV02	go_to	17	cancelled	2026-06-03 16:19:39.299667+07	2026-06-03 16:20:14.94065+07	2026-06-03 16:21:57.48474+07	force-cancelled by user	mpxuutxk86oq9oswaon	A06
1683	6b3b0544	AGV02	go_charge	\N	cancelled	2026-06-05 10:08:31.503249+07	\N	2026-06-05 10:12:38.107718+07	cancelled by user	mq0cg89nmgyfj66cb8k	A06
1340	890dc661	AGV01	go_to	17	completed	2026-06-03 16:59:32.098359+07	2026-06-03 17:00:10.023774+07	2026-06-03 17:00:26.429292+07	lifecycle:picking:confirmed	mpxwa4775qud0p0a4ti	A06
1342	847db7b9	AGV02	go_to	17	completed	2026-06-03 16:59:53.247599+07	2026-06-03 16:59:53.247599+07	2026-06-03 17:00:46.238559+07	lifecycle:picking:confirmed	mpxwakka22kgbcl1625	A06
1689	36dcefbd	AGV01	stop	\N	cancelled	2026-06-05 10:12:50.391732+07	2026-06-05 10:12:50.391732+07	2026-06-05 10:13:07.713405+07	force-cancelled by user	\N	\N
1346	3b03a5b3	AGV02	go_to	17	failed	2026-06-03 17:01:48.918717+07	2026-06-03 17:02:05.357752+07	2026-06-03 17:02:05.362765+07	AGV02: đã ở tại 17	mpxwakka22kgbcl1625	A06
1341	1605c373	AGV01	go_charge	\N	cancelled	2026-06-03 16:59:32.110337+07	2026-06-03 17:00:26.429292+07	2026-06-03 17:06:50.988923+07	force-cancelled by user	mpxwa4775qud0p0a4ti	A06
1349	99c01b06	AGV01	go_charge	\N	completed	2026-06-03 17:06:56.553548+07	2026-06-03 17:06:56.553548+07	2026-06-03 17:07:02.631091+07		mpxwjn6sbitwmwd7p44	Sạc Pin
1350	93b7d319	AGV01	go_charge	\N	completed	2026-06-03 17:06:56.598107+07	2026-06-03 17:07:02.63209+07	2026-06-03 17:07:58.511886+07	charge_arrived	mpxwjn6sbitwmwd7p44	Sạc Pin
1399	8cd2a529	AGV01	go_to	17	completed	2026-06-04 09:29:05.330606+07	2026-06-04 09:29:05.330606+07	2026-06-04 09:29:35.281894+07	lifecycle:picking:confirmed	mpyvmowy2rhlbfnsvtj	A06
1409	312b71e1	AGV01	go_charge	\N	cancelled	2026-06-04 09:34:48.85472+07	2026-06-04 09:34:48.85472+07	2026-06-04 09:35:04.671507+07	force-cancelled by user	mpyvu1zn040shy4heg7t	Sạc Pin
1690	0e8c8e53	AGV01	go_to	18	completed	2026-06-05 10:16:36.110275+07	2026-06-05 10:16:36.110275+07	2026-06-05 10:17:05.236248+07	lifecycle:picking:confirmed	mq0crn9jk7p1lcajwht	A05
1481	db253ccf	AGV02	go_charge	\N	completed	2026-06-04 10:48:00.069836+07	2026-06-04 10:48:08.56972+07	2026-06-04 10:48:32.798101+07	charge_arrived	mpyyg67odkz5je45k9f	Sạc Pin
1520	549988f6	AGV01	go_to	17	completed	2026-06-05 08:21:05.68892+07	2026-06-05 08:21:05.686921+07	2026-06-05 08:21:32.488111+07	lifecycle:picking:confirmed	mq08n3pjs4nooa4g6am	A06
1521	fece5dbc	AGV01	go_to	17	completed	2026-06-05 08:21:05.767459+07	2026-06-05 08:21:32.488111+07	2026-06-05 08:21:42.576187+07	lifecycle:picking:confirmed	mq08n3pjs4nooa4g6am	A06
1523	1231fbde	AGV02	go_to	17	completed	2026-06-05 08:21:19.844142+07	2026-06-05 08:21:19.844142+07	2026-06-05 08:21:54.778224+07	lifecycle:picking:confirmed	mq08nen2vdfv577qq3	A06
1522	8d44edd2	AGV01	go_charge	\N	completed	2026-06-05 08:21:05.785023+07	2026-06-05 08:22:10.631669+07	2026-06-05 08:22:22.506639+07		mq08n3pjs4nooa4g6am	A06
1696	d8472676	AGV02	go_to	16	completed	2026-06-05 10:18:07.237032+07	2026-06-05 10:18:07.237032+07	2026-06-05 10:18:43.780181+07	lifecycle:picking:confirmed	mq0ctlkpihg5smkt3yo	A06
1531	5493019d	AGV01	go_to	13	completed	2026-06-05 08:22:31.718621+07	2026-06-05 08:22:40.869749+07	2026-06-05 08:22:51.503872+07		\N	bounce_retry
1609	943c4e36	AGV01	go_to	69	completed	2026-06-05 09:42:46.872859+07	2026-06-05 09:42:46.872859+07	2026-06-05 09:43:15.789066+07	lifecycle:picking:confirmed	mq0bk5hibi1gtmd4dk5	A02
1616	9c88f972	AGV01	go_to	69	cancelled	2026-06-05 09:44:12.390976+07	\N	2026-06-05 09:44:40.742184+07	cancelled by user	mq0bk5hibi1gtmd4dk5	A02
1890	86d793f9	AGV02	go_to	17	completed	2026-06-05 13:22:32.712604+07	2026-06-05 13:23:06.793417+07	2026-06-05 13:23:52.345539+07		mq0jerquu8vdydiwnpa	A06
1675	ed6fc87e	AGV02	go_to	17	completed	2026-06-05 10:04:35.930807+07	2026-06-05 10:05:20.962644+07	2026-06-05 10:05:55.190123+07	lifecycle:picking:confirmed	mq0cbgazqxecysr5098	A06
1697	7e360616	AGV02	go_to	16	completed	2026-06-05 10:18:07.250026+07	2026-06-05 10:27:22.287406+07	2026-06-05 10:28:31.41063+07	event:continue	mq0ctlkpihg5smkt3yo	A06
1678	7b64bc04	AGV02	go_to	17	completed	2026-06-05 10:07:43.60696+07	2026-06-05 10:08:11.408648+07	2026-06-05 10:08:31.460678+07	lifecycle:picking:confirmed	mq0cg89nmgyfj66cb8k	A06
1680	46e67ce2	AGV01	go_to	17	completed	2026-06-05 10:07:56.36094+07	2026-06-05 10:07:56.36094+07	2026-06-05 10:08:38.626673+07	lifecycle:picking:confirmed	mq0cgi80t8c7ui3t0w9	A06
1679	8f003d1b	AGV02	go_charge	\N	cancelled	2026-06-05 10:07:43.648985+07	2026-06-05 10:08:31.46168+07	2026-06-05 10:12:38.106715+07	force-cancelled by user	mq0cg89nmgyfj66cb8k	A06
1993	51ab1ccd	AGV02	go_charge	\N	cancelled	2026-06-05 16:57:30.938553+07	\N	2026-06-05 16:57:34.463966+07	cancelled by user	mq0prigz87ferr8gtgn	A06
1744	4a5ece29	AGV01	go_charge	\N	completed	2026-06-05 10:46:32.824528+07	2026-06-05 10:46:51.127671+07	2026-06-05 10:46:51.177699+07	bounce_wait	mq0dsxnezi4m5q7i4j	A06
1892	8f8770b9	AGV02	go_to	17	cancelled	2026-06-05 13:23:06.802422+07	2026-06-05 13:23:52.346524+07	2026-06-05 13:25:39.617074+07	force-cancelled by user	mq0jerquu8vdydiwnpa	A06
1748	05687c4c	AGV01	go_to	17	completed	2026-06-05 10:49:18.501236+07	2026-06-05 10:49:53.590975+07	2026-06-05 10:50:15.892508+07	lifecycle:picking:confirmed	mq0dxpfnyvliqvt6o8h	A06
1891	cebe3605	AGV02	go_charge	\N	cancelled	2026-06-05 13:22:32.736124+07	\N	2026-06-05 13:25:39.617074+07	cancelled by user	mq0jerquu8vdydiwnpa	A06
1750	933e3feb	AGV02	go_to	17	completed	2026-06-05 10:49:36.262871+07	2026-06-05 10:49:36.262871+07	2026-06-05 10:50:19.327583+07	lifecycle:picking:confirmed	mq0dy35pib47yd4352g	A06
1753	acefcb55	AGV01	go_charge	\N	cancelled	2026-06-05 10:50:15.916612+07	\N	2026-06-05 10:51:27.274461+07	cancelled by user	mq0dxpfnyvliqvt6o8h	A06
1749	b18acb08	AGV01	go_charge	\N	cancelled	2026-06-05 10:49:18.522774+07	2026-06-05 10:50:15.893506+07	2026-06-05 10:51:27.223684+07	force-cancelled by user	mq0dxpfnyvliqvt6o8h	A06
1798	4ea3d131	AGV02	go_to	17	cancelled	2026-06-05 11:33:17.730178+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1886	8d4fb1a9	AGV01	go_to	17	completed	2026-06-05 13:22:13.895488+07	2026-06-05 13:22:13.895488+07	2026-06-05 13:22:48.411272+07	lifecycle:picking:confirmed	mq0jed864yq1si1mtg	A06
1971	9bca9914	AGV02	go_to	17	completed	2026-06-05 16:02:13.672173+07	2026-06-05 16:04:01.118095+07	2026-06-05 16:04:47.992568+07	lifecycle:picking:confirmed	mq0p443qs59j1txq17m	A02
1934	0253d6c3	AGV01	go_to	17	completed	2026-06-05 14:18:04.146732+07	2026-06-05 14:18:04.146732+07	2026-06-05 14:18:20.85375+07	off_route	mq0le6av3h20z34kb1v	A06
1951	d610585a	AGV02	go_to	69	completed	2026-06-05 15:40:51.464442+07	2026-06-05 15:41:06.714338+07	2026-06-05 15:41:46.504527+07	lifecycle:picking:confirmed	mq0obzmvod6h3vlol2	A06
1972	853dc072	AGV02	go_charge	\N	completed	2026-06-05 16:02:13.685185+07	2026-06-05 16:05:10.637112+07	2026-06-05 16:05:25.527822+07		mq0p443qs59j1txq17m	A02
1970	e95aab99	AGV02	go_to	69	completed	2026-06-05 16:02:13.661167+07	2026-06-05 16:03:06.325477+07	2026-06-05 16:03:21.814884+07		mq0p443qs59j1txq17m	A02
2017	ca825623	AGV02	go_to	18	completed	2026-06-06 10:15:52.512478+07	2026-06-06 10:15:52.512478+07	2026-06-06 10:16:20.901697+07	lifecycle:picking:confirmed	mq1s6ka7y9ki2n4sych	A02
1982	c983f461	AGV02	go_to	69	completed	2026-06-05 16:07:31.97397+07	2026-06-05 16:07:47.286395+07	2026-06-05 16:08:26.3519+07	lifecycle:picking:confirmed	mq0pacqsb8k14wijidp	A05
2002	f81857c8	AGV02	go_to	96	completed	2026-06-06 09:36:34.605501+07	2026-06-06 09:36:49.905421+07	2026-06-06 09:37:08.607764+07	lifecycle:picking:confirmed	mq1qrfmxrwxscfgmrf	A02
2003	50b8b404	AGV02	go_to	69	completed	2026-06-06 09:37:35.340306+07	2026-06-06 09:37:35.342314+07	2026-06-06 09:37:47.159824+07		mq1qrfmxrwxscfgmrf	A02
2020	48f44713	AGV02	go_charge	\N	cancelled	2026-06-06 10:15:52.596193+07	\N	2026-06-06 10:55:36.805355+07	cancelled by user	mq1s6ka7y9ki2n4sych	A02
2018	50db2817	AGV02	go_to	18	completed	2026-06-06 10:15:52.562+07	2026-06-06 10:16:20.910138+07	2026-06-06 10:16:32.841323+07		mq1s6ka7y9ki2n4sych	A02
2019	18752b86	AGV02	go_to	69	completed	2026-06-06 10:15:52.580015+07	2026-06-06 10:16:49.056865+07	2026-06-06 10:17:03.803737+07		mq1s6ka7y9ki2n4sych	A02
2023	7723cb78	AGV02	go_to	69	cancelled	2026-06-06 10:16:49.059911+07	\N	2026-06-06 10:55:36.805355+07	cancelled by user	mq1s6ka7y9ki2n4sych	A02
2025	80895d15	AGV02	go_charge	\N	completed	2026-06-06 10:55:41.627532+07	2026-06-06 10:55:41.627532+07	2026-06-06 10:55:53.352355+07	off_route	mq1tlrpbms7dzt5ulaf	Sạc Pin
2030	26f73691	AGV02	go_to	19	completed	2026-06-06 11:02:35.562283+07	2026-06-06 11:03:10.818679+07	2026-06-06 11:03:25.035938+07	lifecycle:picking:confirmed	mq1tum5wpi2jdka25ri	A02
447	9c8387c1	AGV01	go_charge	\N	cancelled	2026-06-01 16:43:00.656318+07	\N	2026-06-01 16:43:47.937058+07	cancelled by user	mpv0t5v38bumq5ivcj8	A06
448	ba835c3e	AGV01	go_to	1	failed	2026-06-02 08:12:53.333466+07	\N	\N	\N	8213187f65	Mô phỏng vòng 1/10
449	e1c90c8d	AGV01	go_to	1	failed	2026-06-02 08:13:03.3803+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 1/10
450	6babc161	AGV01	go_to	2	failed	2026-06-02 08:13:14.823629+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 1/10
451	44a0650c	AGV01	go_to	3	failed	2026-06-02 08:13:26.239409+07	2026-06-02 08:13:26.239409+07	2026-06-02 08:13:36.244385+07	dispatch failed	79087a1c35	Mô phỏng vòng 1/10
452	ad9bafd0	AGV01	go_to	19	failed	2026-06-02 08:13:37.676652+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 1/10
453	257b4cf7	AGV01	go_to	4	failed	2026-06-02 08:13:49.132245+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 1/10
454	49409c01	AGV01	go_to	18	failed	2026-06-02 08:14:00.531524+07	2026-06-02 08:14:00.531524+07	2026-06-02 08:14:10.537682+07	dispatch failed	79087a1c35	Mô phỏng vòng 1/10
455	b34ce702	AGV01	go_to	5	failed	2026-06-02 08:14:11.965813+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 1/10
456	33a404d3	AGV01	go_to	17	failed	2026-06-02 08:14:23.418844+07	2026-06-02 08:14:23.418844+07	2026-06-02 08:14:33.419913+07	dispatch failed	79087a1c35	Mô phỏng vòng 1/10
457	6794f9c0	AGV01	go_to	6	failed	2026-06-02 08:14:34.81816+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 1/10
458	6c971c17	AGV01	go_to	17	failed	2026-06-02 08:14:46.233799+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 1/10
459	d9df99a7	AGV01	go_to	5	failed	2026-06-02 08:14:57.658788+07	2026-06-02 08:14:57.658788+07	2026-06-02 08:15:07.663058+07	dispatch failed	79087a1c35	Mô phỏng vòng 1/10
460	b76c38e3	AGV01	go_to	18	failed	2026-06-02 08:15:09.089261+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 1/10
461	bb66c529	AGV01	go_to	4	failed	2026-06-02 08:15:20.514526+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 1/10
462	9ad365c6	AGV01	go_to	19	failed	2026-06-02 08:15:31.938941+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 1/10
463	8e01765a	AGV01	go_to	3	failed	2026-06-02 08:15:43.351966+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 1/10
464	d7ba8e2c	AGV01	go_to	2	failed	2026-06-02 08:15:54.767906+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 1/10
465	b7bf7b20	AGV01	go_to	1	failed	2026-06-02 08:16:06.186815+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 2/10
466	c86ec6a7	AGV01	go_to	2	failed	2026-06-02 08:16:17.604561+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 2/10
467	c10d27ee	AGV01	go_to	3	failed	2026-06-02 08:16:29.043413+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 2/10
468	67542ac0	AGV01	go_to	19	failed	2026-06-02 08:16:40.45364+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 2/10
469	400b7bc2	AGV01	go_to	4	failed	2026-06-02 08:16:51.856114+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 2/10
470	e43afbc2	AGV01	go_to	18	failed	2026-06-02 08:17:03.288378+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 2/10
471	8712218a	AGV01	go_to	5	failed	2026-06-02 08:17:14.72997+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 2/10
472	77b691f8	AGV01	go_to	17	failed	2026-06-02 08:17:26.142976+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 2/10
473	50a258a5	AGV01	go_to	6	failed	2026-06-02 08:17:37.535815+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 2/10
474	aa98f9ce	AGV01	go_to	17	failed	2026-06-02 08:17:48.976044+07	2026-06-02 08:17:48.976044+07	2026-06-02 08:17:58.989095+07	dispatch failed	79087a1c35	Mô phỏng vòng 2/10
475	02b2f4dc	AGV01	go_to	5	failed	2026-06-02 08:18:00.414282+07	2026-06-02 08:18:00.414282+07	2026-06-02 08:18:10.429935+07	dispatch failed	79087a1c35	Mô phỏng vòng 2/10
476	505781e9	AGV01	go_to	18	failed	2026-06-02 08:18:11.837364+07	2026-06-02 08:18:11.837364+07	2026-06-02 08:18:21.842879+07	dispatch failed	79087a1c35	Mô phỏng vòng 2/10
477	02379017	AGV01	go_to	4	failed	2026-06-02 08:18:23.262452+07	2026-06-02 08:18:23.262452+07	2026-06-02 08:18:33.26957+07	dispatch failed	79087a1c35	Mô phỏng vòng 2/10
478	ec5c72ac	AGV01	go_to	19	failed	2026-06-02 08:18:34.698784+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 2/10
479	6147d8a7	AGV01	go_to	3	failed	2026-06-02 08:18:46.124741+07	2026-06-02 08:18:46.124741+07	2026-06-02 08:18:56.137594+07	dispatch failed	79087a1c35	Mô phỏng vòng 2/10
480	ac72cd25	AGV01	go_to	2	failed	2026-06-02 08:18:57.551684+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 2/10
481	eeafd8fc	AGV01	go_to	1	failed	2026-06-02 08:19:08.949288+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 3/10
482	e2f90607	AGV01	go_to	2	failed	2026-06-02 08:19:20.379048+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 3/10
483	d1cdf67c	AGV01	go_to	3	failed	2026-06-02 08:19:31.833956+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 3/10
484	b804e86a	AGV01	go_to	19	failed	2026-06-02 08:19:43.256268+07	2026-06-02 08:19:43.256268+07	2026-06-02 08:19:53.268641+07	dispatch failed	79087a1c35	Mô phỏng vòng 3/10
485	0edc7787	AGV01	go_to	4	failed	2026-06-02 08:19:54.684402+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 3/10
486	22347d4e	AGV01	go_to	18	failed	2026-06-02 08:20:06.091738+07	2026-06-02 08:20:06.091738+07	2026-06-02 08:20:16.103798+07	dispatch failed	79087a1c35	Mô phỏng vòng 3/10
487	fd92b508	AGV01	go_to	5	failed	2026-06-02 08:20:17.498767+07	2026-06-02 08:20:17.498767+07	2026-06-02 08:20:27.512376+07	dispatch failed	79087a1c35	Mô phỏng vòng 3/10
488	6d349d65	AGV01	go_to	17	failed	2026-06-02 08:20:28.952408+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 3/10
489	cb4a846d	AGV01	go_to	6	failed	2026-06-02 08:20:40.411264+07	2026-06-02 08:20:40.411264+07	2026-06-02 08:20:50.422563+07	dispatch failed	79087a1c35	Mô phỏng vòng 3/10
490	ddcc59cb	AGV01	go_to	17	failed	2026-06-02 08:20:51.828987+07	2026-06-02 08:20:51.828987+07	2026-06-02 08:21:01.84088+07	dispatch failed	79087a1c35	Mô phỏng vòng 3/10
491	6ca5d0ec	AGV01	go_to	5	failed	2026-06-02 08:21:03.298306+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 3/10
492	01ed079e	AGV01	go_to	18	failed	2026-06-02 08:21:14.737551+07	2026-06-02 08:21:14.737551+07	2026-06-02 08:21:24.742713+07	dispatch failed	79087a1c35	Mô phỏng vòng 3/10
493	1a1d97b4	AGV01	go_to	4	failed	2026-06-02 08:21:26.168579+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 3/10
494	1f57c7ee	AGV01	go_to	19	failed	2026-06-02 08:21:37.560318+07	2026-06-02 08:21:37.560318+07	2026-06-02 08:21:47.563343+07	dispatch failed	79087a1c35	Mô phỏng vòng 3/10
495	781e2f86	AGV01	go_to	3	failed	2026-06-02 08:21:48.967292+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 3/10
496	70d16e2c	AGV01	go_to	2	failed	2026-06-02 08:22:00.374526+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 3/10
497	4f7f22fd	AGV01	go_to	1	failed	2026-06-02 08:22:11.792105+07	2026-06-02 08:22:11.792105+07	2026-06-02 08:22:21.794339+07	dispatch failed	79087a1c35	Mô phỏng vòng 4/10
498	c355d759	AGV01	go_to	2	failed	2026-06-02 08:22:23.199635+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 4/10
499	a2e316b6	AGV01	go_to	3	failed	2026-06-02 08:22:34.62143+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 4/10
500	190fb296	AGV01	go_to	19	failed	2026-06-02 08:22:46.046986+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 4/10
501	1a3d20a4	AGV01	go_to	4	failed	2026-06-02 08:22:57.474986+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 4/10
502	67e45049	AGV01	go_to	18	failed	2026-06-02 08:23:08.911191+07	2026-06-02 08:23:08.911191+07	2026-06-02 08:23:18.922574+07	dispatch failed	79087a1c35	Mô phỏng vòng 4/10
503	996398f4	AGV01	go_to	5	failed	2026-06-02 08:23:20.327546+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 4/10
504	46eaf025	AGV01	go_to	17	failed	2026-06-02 08:23:31.736686+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 4/10
505	696b1df6	AGV01	go_to	2	failed	2026-06-02 08:23:41.801986+07	2026-06-02 08:23:41.801986+07	2026-06-02 08:23:51.808222+07	dispatch failed	c2068c0348	Mô phỏng vòng 1/10
506	e590a8f6	AGV01	go_to	6	failed	2026-06-02 08:23:52.828859+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 4/10
1249	84fb8156	AGV02	go_to	17	completed	2026-06-03 16:19:39.275714+07	2026-06-03 16:19:39.275714+07	2026-06-03 16:20:14.933617+07	event:continue	mpxuutxk86oq9oswaon	A06
507	d1efd680	AGV01	go_to	3	failed	2026-06-02 08:24:02.852078+07	2026-06-02 08:24:02.852078+07	2026-06-02 08:24:12.854862+07	dispatch failed	c2068c0348	Mô phỏng vòng 1/10
508	007682c2	AGV01	go_to	17	failed	2026-06-02 08:24:13.864342+07	2026-06-02 08:24:13.864342+07	2026-06-02 08:24:23.869613+07	dispatch failed	79087a1c35	Mô phỏng vòng 4/10
514	38a6f50b	AGV01	go_to	4	failed	2026-06-02 08:25:16.94816+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 4/10
517	931da953	AGV01	go_to	18	failed	2026-06-02 08:25:48.006648+07	2026-06-02 08:25:48.006648+07	2026-06-02 08:25:58.021872+07	dispatch failed	c2068c0348	Mô phỏng vòng 1/10
529	cc8f6ef0	AGV01	go_to	19	failed	2026-06-02 08:27:54.443195+07	2026-06-02 08:27:54.443195+07	2026-06-02 08:28:04.444315+07	dispatch failed	c2068c0348	Mô phỏng vòng 2/10
531	d3581914	AGV01	go_to	4	failed	2026-06-02 08:28:15.481732+07	\N	\N	\N	c2068c0348	Mô phỏng vòng 2/10
1254	7a4f983a	AGV02	go_charge	\N	completed	2026-06-03 16:30:50.066095+07	2026-06-03 16:30:50.066095+07	2026-06-03 16:30:58.686985+07		mpxv97hroc880iush5	Sạc Pin
1347	d8d47b52	AGV02	go_charge	\N	completed	2026-06-03 17:05:48.288404+07	2026-06-03 17:05:48.288404+07	2026-06-03 17:05:53.608109+07		mpxwi6ik2qlnjvbtcug	Sạc Pin
1345	a2571fa8	AGV01	go_charge	\N	cancelled	2026-06-03 17:00:26.445188+07	\N	2026-06-03 17:06:50.988923+07	cancelled by user	mpxwa4775qud0p0a4ti	A06
1612	ea57796c	AGV01	go_charge	\N	cancelled	2026-06-05 09:42:46.977469+07	\N	2026-06-05 09:44:40.742184+07	cancelled by user	mq0bk5hibi1gtmd4dk5	A02
1400	0b50db2b	AGV01	go_to	17	completed	2026-06-04 09:29:05.692699+07	2026-06-04 09:29:35.289897+07	2026-06-04 09:30:09.029919+07	lifecycle:picking:confirmed	mpyvmowy2rhlbfnsvtj	A06
1401	eec7b9a2	AGV01	go_charge	\N	completed	2026-06-04 09:29:05.698701+07	2026-06-04 09:30:09.029919+07	2026-06-04 09:30:18.246468+07		mpyvmowy2rhlbfnsvtj	A06
1402	935efd6f	AGV02	go_to	17	completed	2026-06-04 09:29:15.484357+07	2026-06-04 09:29:15.484357+07	2026-06-04 09:30:44.970345+07	event:continue	mpyvmwray81ilpnhlk	A06
1831	75f1925b	AGV02	go_to	19	cancelled	2026-06-05 11:35:37.928367+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1407	0917a27b	AGV01	go_charge	\N	cancelled	2026-06-04 09:30:18.33602+07	\N	2026-06-04 09:34:38.315188+07	cancelled by user	mpyvmowy2rhlbfnsvtj	A06
1403	9c77e856	AGV02	go_to	17	cancelled	2026-06-04 09:29:15.498368+07	2026-06-04 09:30:44.978363+07	2026-06-04 09:35:08.179337+07	force-cancelled by user	mpyvmwray81ilpnhlk	A06
1404	79648f19	AGV02	go_charge	\N	cancelled	2026-06-04 09:29:15.523884+07	\N	2026-06-04 09:35:08.184351+07	cancelled by user	mpyvmwray81ilpnhlk	A06
1483	bb0ddd33	AGV01	go_to	17	completed	2026-06-04 10:58:24.401449+07	2026-06-04 10:58:24.401449+07	2026-06-04 10:59:04.179801+07	lifecycle:picking:confirmed	mpyytk00ckkmri4f5is	A06
1700	75583757	AGV02	go_to	9	completed	2026-06-05 10:18:44.164031+07	2026-06-05 10:18:57.186074+07	2026-06-05 10:27:22.287406+07	lifecycle:picking:confirmed	mq0ctlkpihg5smkt3yo	A06
1490	08d29fa1	AGV01	go_charge	\N	completed	2026-06-04 11:02:57.774175+07	2026-06-04 11:02:57.774175+07	2026-06-04 11:03:15.718717+07		\N	bounce_retry
1487	d4143e3b	AGV02	go_to	17	completed	2026-06-04 10:58:47.161533+07	2026-06-04 11:02:49.177408+07	2026-06-04 11:04:01.639908+07	lifecycle:picking:confirmed	mpyyu1jpxzbfkujmok	A06
1747	60501488	AGV01	go_to	17	completed	2026-06-05 10:49:18.472467+07	2026-06-05 10:49:18.472467+07	2026-06-05 10:49:53.590975+07	lifecycle:picking:confirmed	mq0dxpfnyvliqvt6o8h	A06
1488	dc2ae6d7	AGV02	go_charge	\N	completed	2026-06-04 10:58:47.169531+07	2026-06-04 11:04:01.639908+07	2026-06-04 11:04:44.297974+07	charge_arrived	mpyyu1jpxzbfkujmok	A06
1524	726d10b9	AGV02	go_to	17	completed	2026-06-05 08:21:19.936536+07	2026-06-05 08:21:54.778224+07	2026-06-05 08:22:15.31177+07	lifecycle:picking:confirmed	mq08nen2vdfv577qq3	A06
1529	43671bb3	AGV01	go_charge	\N	completed	2026-06-05 08:22:10.659668+07	2026-06-05 08:22:22.507639+07	2026-06-05 08:22:22.519641+07	bounce_wait	mq08n3pjs4nooa4g6am	A06
1530	227b06b5	AGV01	go_charge	\N	completed	2026-06-05 08:22:24.876703+07	2026-06-05 08:22:24.876703+07	2026-06-05 08:22:40.869749+07		\N	bounce_retry
1754	04d17792	AGV01	go_to	18	cancelled	2026-06-05 10:50:37.941342+07	\N	2026-06-05 10:51:27.274461+07	cancelled by user	mq0dxpfnyvliqvt6o8h	A06
1527	0ded5c25	AGV02	go_to	17	completed	2026-06-05 08:21:54.790684+07	2026-06-05 08:23:09.767652+07	2026-06-05 08:25:37.688316+07	lifecycle:picking:confirmed	mq08nen2vdfv577qq3	A06
1829	44f72e97	AGV02	go_to	9	cancelled	2026-06-05 11:35:30.696564+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1525	c7c33568	AGV02	go_charge	\N	completed	2026-06-05 08:21:19.959061+07	2026-06-05 08:25:37.688316+07	2026-06-05 08:25:50.492186+07		mq08nen2vdfv577qq3	A06
1755	1df00b16	AGV02	go_to	17	completed	2026-06-05 10:51:25.044178+07	2026-06-05 10:55:01.973931+07	2026-06-05 10:55:01.979852+07	already_at_dest	mq0dy35pib47yd4352g	A06
1610	d15eb9f1	AGV01	go_to	69	completed	2026-06-05 09:42:46.933537+07	2026-06-05 09:43:15.790064+07	2026-06-05 09:43:32.036114+07		mq0bk5hibi1gtmd4dk5	A02
1614	ec0d9621	AGV01	go_to	69	completed	2026-06-05 09:43:32.11467+07	2026-06-05 09:43:56.227586+07	2026-06-05 09:44:12.206931+07		mq0bk5hibi1gtmd4dk5	A02
1611	3dd4c242	AGV01	go_to	18	cancelled	2026-06-05 09:42:46.956094+07	\N	2026-06-05 09:44:40.742184+07	cancelled by user	mq0bk5hibi1gtmd4dk5	A02
2777	9374013e	AGV02	go_charge	\N	completed	2026-06-15 10:39:55.791881+07	2026-06-15 10:40:12.195374+07	2026-06-15 10:40:55.49169+07	charge_arrived	mqeo054z6irogpaaxw	Sạc Pin
2780	c05c77eb	AGV01	go_charge	\N	completed	2026-06-15 10:40:49.473035+07	2026-06-15 10:40:49.473029+07	2026-06-15 10:41:04.382401+07		mqeo1akkpqmnezqzof	Sạc Pin
1828	99190da1	AGV02	go_to	19	cancelled	2026-06-05 11:35:23.386931+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1826	2efbf9fa	AGV02	go_to	9	cancelled	2026-06-05 11:35:14.98495+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1824	dc18ea6d	AGV02	go_to	19	cancelled	2026-06-05 11:35:07.534868+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1822	7b905df9	AGV02	go_to	9	cancelled	2026-06-05 11:34:58.113036+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1819	e80b6b81	AGV02	go_to	19	cancelled	2026-06-05 11:34:48.527302+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1817	5ab3f231	AGV02	go_to	9	cancelled	2026-06-05 11:34:41.383054+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1815	44b88bd0	AGV02	go_to	19	cancelled	2026-06-05 11:34:31.669024+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1809	0866ca63	AGV02	go_to	9	cancelled	2026-06-05 11:34:07.735012+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1807	1d6f44ba	AGV02	go_to	19	cancelled	2026-06-05 11:34:00.346804+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1805	71882038	AGV02	go_to	9	cancelled	2026-06-05 11:33:53.159926+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1830	b83b38bf	AGV01	go_to	8	cancelled	2026-06-05 11:35:31.690624+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1825	0455de45	AGV01	go_to	8	cancelled	2026-06-05 11:35:12.337025+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1827	2cfb55ec	AGV01	go_to	7	cancelled	2026-06-05 11:35:21.87356+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1823	2f03834d	AGV01	go_to	7	cancelled	2026-06-05 11:35:04.991587+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1821	8d65dd84	AGV01	go_to	8	cancelled	2026-06-05 11:34:57.546347+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1820	ea14d3b4	AGV01	go_to	7	cancelled	2026-06-05 11:34:50.248654+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1818	196786bc	AGV01	go_to	8	cancelled	2026-06-05 11:34:42.901255+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1816	70db5451	AGV01	go_to	7	cancelled	2026-06-05 11:34:33.356515+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1814	2fc80e34	AGV01	go_to	8	cancelled	2026-06-05 11:34:26.039994+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1808	57830418	AGV01	go_to	7	cancelled	2026-06-05 11:34:00.58528+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1806	f1af831a	AGV01	go_to	8	cancelled	2026-06-05 11:33:53.345771+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1804	43a4803b	AGV01	go_to	7	cancelled	2026-06-05 11:33:45.983242+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
509	24cb9efa	AGV01	go_to	19	failed	2026-06-02 08:24:23.87384+07	\N	\N	\N	c2068c0348	Mô phỏng vòng 1/10
516	5ac2284a	AGV01	go_to	19	failed	2026-06-02 08:25:37.983402+07	2026-06-02 08:25:37.983402+07	2026-06-02 08:25:47.994647+07	dispatch failed	79087a1c35	Mô phỏng vòng 4/10
520	2a7918f0	AGV01	go_to	2	failed	2026-06-02 08:26:20.096487+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 4/10
527	a6cd0bd8	AGV01	go_to	3	failed	2026-06-02 08:27:33.411172+07	\N	\N	\N	c2068c0348	Mô phỏng vòng 2/10
1255	4839e6a2	AGV02	go_charge	\N	completed	2026-06-03 16:30:50.357792+07	2026-06-03 16:30:58.687989+07	2026-06-03 16:31:22.697254+07	charge_arrived	mpxv97hroc880iush5	Sạc Pin
1351	d0ce4fdb	AGV01	go_to	17	completed	2026-06-04 08:20:37.718278+07	2026-06-04 08:20:37.718278+07	2026-06-04 08:21:09.87936+07	lifecycle:picking:confirmed	mpyt6nghv885xz3tlho	A06
1405	5c3028cf	AGV02	go_to	19	completed	2026-06-04 09:29:45.788932+07	2026-06-04 09:30:44.971361+07	2026-06-04 09:30:44.972359+07	already_at_dest	mpyvmwray81ilpnhlk	A06
1406	81b8f1bd	AGV01	go_charge	\N	cancelled	2026-06-04 09:30:09.047916+07	2026-06-04 09:30:18.249465+07	2026-06-04 09:34:38.315188+07	force-cancelled by user	mpyvmowy2rhlbfnsvtj	A06
1410	40de4f4d	AGV01	go_charge	\N	cancelled	2026-06-04 09:34:49.005239+07	\N	2026-06-04 09:35:04.672506+07	cancelled by user	mpyvu1zn040shy4heg7t	Sạc Pin
1408	3e3102a1	AGV02	go_to	17	cancelled	2026-06-04 09:30:52.978446+07	\N	2026-06-04 09:35:08.184351+07	cancelled by user	mpyvmwray81ilpnhlk	A06
1761	0bc2a104	AGV01	go_to	17	completed	2026-06-05 11:03:41.110497+07	2026-06-05 11:03:41.110497+07	2026-06-05 11:04:09.982028+07	lifecycle:picking:confirmed	mq0eg71h94k4md5ku4q	A06
1856	724cc61f	AGV02	go_to	19	cancelled	2026-06-05 11:37:17.486874+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1484	1890361a	AGV01	go_to	17	completed	2026-06-04 10:58:24.76671+07	2026-06-04 10:59:04.179801+07	2026-06-04 11:02:35.962263+07	lifecycle:picking:confirmed	mpyytk00ckkmri4f5is	A06
1486	159050ed	AGV02	go_to	17	completed	2026-06-04 10:58:47.130527+07	2026-06-04 10:58:47.130527+07	2026-06-04 11:02:49.177408+07	lifecycle:picking:confirmed	mpyyu1jpxzbfkujmok	A06
1485	d56a0b85	AGV01	go_charge	\N	completed	2026-06-04 10:58:24.785732+07	2026-06-04 11:02:35.963253+07	2026-06-04 11:02:49.378745+07		mpyytk00ckkmri4f5is	A06
1765	c9a41068	AGV02	go_to	17	failed	2026-06-05 11:03:52.0013+07	2026-06-05 11:04:33.817551+07	2026-06-05 11:04:34.101732+07	'TrafficCoordinator' object has no attribute '_critical_nodes_cache'	mq0egfflzdstopdk6cd	A06
1492	57df6fa2	AGV01	go_to	13	completed	2026-06-04 11:03:15.733711+07	2026-06-04 11:03:23.83159+07	2026-06-04 11:04:50.297944+07	lifecycle:picking:confirmed	\N	bounce_retry
1766	e21194d1	AGV02	go_charge	\N	cancelled	2026-06-05 11:03:52.013307+07	\N	2026-06-05 11:09:59.340658+07	cancelled by user	mq0egfflzdstopdk6cd	A06
1526	f4bcff21	AGV01	go_to	17	completed	2026-06-05 08:21:32.737635+07	2026-06-05 08:21:42.576187+07	2026-06-05 08:22:10.631669+07	lifecycle:picking:confirmed	mq08n3pjs4nooa4g6am	A06
1528	4192cdc2	AGV02	go_to	15	completed	2026-06-05 08:21:54.810292+07	2026-06-05 08:22:15.31177+07	2026-06-05 08:23:09.767652+07	lifecycle:picking:confirmed	mq08nen2vdfv577qq3	A06
1532	e1233483	AGV01	go_to	13	completed	2026-06-05 08:22:40.88575+07	2026-06-05 08:22:51.503872+07	2026-06-05 08:27:26.637324+07	lifecycle:picking:confirmed	\N	bounce_retry
1613	363192b9	AGV01	go_to	69	completed	2026-06-05 09:43:16.06421+07	2026-06-05 09:43:32.036114+07	2026-06-05 09:43:56.227586+07	lifecycle:picking:confirmed	mq0bk5hibi1gtmd4dk5	A02
1615	b4e75b27	AGV01	go_to	69	cancelled	2026-06-05 09:43:56.261125+07	2026-06-05 09:44:12.20793+07	2026-06-05 09:44:40.742184+07	force-cancelled by user	mq0bk5hibi1gtmd4dk5	A02
1716	e66341a7	AGV01	go_to	8	cancelled	2026-06-05 10:21:28.37344+07	\N	2026-06-05 10:26:02.510782+07	cancelled by user	mq0crn9jk7p1lcajwht	A05
1714	4720377c	AGV01	go_to	8	cancelled	2026-06-05 10:21:14.354833+07	\N	2026-06-05 10:26:02.510782+07	cancelled by user	mq0crn9jk7p1lcajwht	A05
1712	d1dc5bb4	AGV01	go_to	8	cancelled	2026-06-05 10:20:56.318699+07	\N	2026-06-05 10:26:02.510782+07	cancelled by user	mq0crn9jk7p1lcajwht	A05
1715	ced3eb3a	AGV01	go_to	19	cancelled	2026-06-05 10:21:21.344306+07	\N	2026-06-05 10:26:02.510782+07	cancelled by user	mq0crn9jk7p1lcajwht	A05
1713	a9763a13	AGV01	go_to	19	cancelled	2026-06-05 10:21:03.318903+07	\N	2026-06-05 10:26:02.510782+07	cancelled by user	mq0crn9jk7p1lcajwht	A05
1711	50d7f66e	AGV01	go_to	19	cancelled	2026-06-05 10:20:47.102907+07	\N	2026-06-05 10:26:02.510782+07	cancelled by user	mq0crn9jk7p1lcajwht	A05
1710	f2abab25	AGV01	go_to	8	cancelled	2026-06-05 10:20:37.680791+07	\N	2026-06-05 10:26:02.510782+07	cancelled by user	mq0crn9jk7p1lcajwht	A05
1849	3eb6284a	AGV02	go_to	9	cancelled	2026-06-05 11:36:49.446824+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1838	d389bf5f	AGV02	go_to	9	cancelled	2026-06-05 11:36:06.072978+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1835	2addd7d9	AGV02	go_to	19	cancelled	2026-06-05 11:35:54.686819+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1833	8cf9bf8e	AGV02	go_to	9	cancelled	2026-06-05 11:35:47.529874+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1854	630c505c	AGV02	go_to	9	cancelled	2026-06-05 11:37:10.282123+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1811	2c9bed5b	AGV02	go_to	19	cancelled	2026-06-05 11:34:14.938796+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1852	5bd5f96d	AGV02	go_to	19	cancelled	2026-06-05 11:37:00.60951+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1845	31eed693	AGV02	go_to	9	cancelled	2026-06-05 11:36:34.979155+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1847	a17fb25a	AGV02	go_to	19	cancelled	2026-06-05 11:36:42.129743+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1840	8f7ce002	AGV02	go_to	19	cancelled	2026-06-05 11:36:13.199868+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1843	bcc3cd4e	AGV02	go_to	19	cancelled	2026-06-05 11:36:27.684664+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1842	bdfd0499	AGV02	go_to	9	cancelled	2026-06-05 11:36:20.528501+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1857	3eb9d44b	AGV01	go_to	8	cancelled	2026-06-05 11:37:21.914833+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1853	e38dde86	AGV01	go_to	8	cancelled	2026-06-05 11:37:04.945264+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1855	80faf402	AGV01	go_to	7	cancelled	2026-06-05 11:37:12.360981+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1851	df87b7ac	AGV01	go_to	7	cancelled	2026-06-05 11:36:57.587512+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1850	4d16ab81	AGV01	go_to	8	cancelled	2026-06-05 11:36:50.171131+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1848	c08eb079	AGV01	go_to	7	cancelled	2026-06-05 11:36:42.707172+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1846	049360ba	AGV01	go_to	8	cancelled	2026-06-05 11:36:35.395553+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1841	69bfb99d	AGV01	go_to	8	cancelled	2026-06-05 11:36:18.407694+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1837	7865d9b0	AGV01	go_to	8	cancelled	2026-06-05 11:36:03.748825+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1836	99af10de	AGV01	go_to	7	cancelled	2026-06-05 11:35:56.306484+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1834	dc78cba1	AGV01	go_to	8	cancelled	2026-06-05 11:35:48.924301+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1832	6b47f99f	AGV01	go_to	7	cancelled	2026-06-05 11:35:41.378787+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
3459	c4a91c94	AGV01	go_to	69	cancelled	2026-06-19 15:46:33.657482+07	\N	2026-06-19 15:48:57.84085+07	cancelled by user	\N	\N
1888	1744a7da	AGV01	go_charge	\N	completed	2026-06-05 13:22:14.310356+07	2026-06-05 13:23:13.479956+07	2026-06-05 13:23:13.518473+07	bounce_wait	mq0jed864yq1si1mtg	A06
1889	9176b8c6	AGV02	go_to	17	completed	2026-06-05 13:22:32.69807+07	2026-06-05 13:22:32.69807+07	2026-06-05 13:23:06.793417+07	lifecycle:picking:confirmed	mq0jerquu8vdydiwnpa	A06
510	fcecb568	AGV01	go_to	5	failed	2026-06-02 08:24:34.8676+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 4/10
511	d0feb7ff	AGV01	go_to	4	failed	2026-06-02 08:24:44.896454+07	\N	\N	\N	c2068c0348	Mô phỏng vòng 1/10
512	ea816126	AGV01	go_to	18	failed	2026-06-02 08:24:55.914254+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 4/10
513	7e4995ef	AGV01	go_to	18	failed	2026-06-02 08:25:05.936669+07	\N	\N	\N	c2068c0348	Mô phỏng vòng 1/10
522	5df2626b	AGV01	go_to	1	failed	2026-06-02 08:26:41.129311+07	2026-06-02 08:26:41.129311+07	2026-06-02 08:26:51.153702+07	dispatch failed	79087a1c35	Mô phỏng vòng 5/10
523	67d2b616	AGV01	go_to	3	failed	2026-06-02 08:26:51.317433+07	2026-06-02 08:26:51.317433+07	2026-06-02 08:27:01.331894+07	dispatch failed	c2068c0348	Mô phỏng vòng 1/10
528	1eccecd2	AGV01	go_to	19	failed	2026-06-02 08:27:44.424181+07	2026-06-02 08:27:44.424181+07	2026-06-02 08:27:54.431203+07	dispatch failed	79087a1c35	Mô phỏng vòng 5/10
530	6ece234b	AGV01	go_to	4	failed	2026-06-02 08:28:05.471297+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 5/10
1260	99a82185	AGV02	go_to	17	queued	2026-06-03 16:32:00.563019+07	\N	\N	\N	mpxvapspozh8dsfy79e	A06
1261	a605988b	AGV02	go_charge	\N	queued	2026-06-03 16:32:00.581553+07	\N	\N	\N	mpxvapspozh8dsfy79e	A06
1256	6959d0aa	AGV01	go_to	17	completed	2026-06-03 16:31:46.48676+07	2026-06-03 16:31:46.48676+07	2026-06-03 16:32:16.490205+07	lifecycle:picking:confirmed	mpxvaf1rfcvmye8b5xg	A06
1262	61f1bac7	AGV01	go_charge	\N	running	2026-06-03 16:32:33.644616+07	2026-06-03 16:32:38.858873+07	\N		mpxvaf1rfcvmye8b5xg	A06
1355	b99d4b63	AGV02	go_to	17	queued	2026-06-04 08:20:54.646361+07	\N	\N	\N	mpyt70ir6femvsia8z	A06
1356	47cf405a	AGV02	go_charge	\N	queued	2026-06-04 08:20:54.65848+07	\N	\N	\N	mpyt70ir6femvsia8z	A06
2026	7ea4de3a	AGV02	go_charge	14	completed	2026-06-06 10:55:53.351397+07	2026-06-06 10:55:53.353383+07	2026-06-06 10:56:10.386777+07		mq1tlrpbms7dzt5ulaf	Sạc Pin
1352	66563887	AGV01	go_to	17	completed	2026-06-04 08:20:37.762736+07	2026-06-04 08:21:09.87936+07	2026-06-04 08:21:52.884388+07	lifecycle:picking:confirmed	mpyt6nghv885xz3tlho	A06
1357	7f5d867c	AGV01	go_charge	\N	running	2026-06-04 08:21:52.91226+07	2026-06-04 08:22:00.326173+07	\N		mpyt6nghv885xz3tlho	A06
1411	846a2397	AGV01	go_to	17	completed	2026-06-04 09:54:59.079373+07	2026-06-04 09:54:59.079373+07	2026-06-04 09:55:26.495431+07	lifecycle:picking:confirmed	mpywjzsdg769egz5gc	A06
1937	77aa7dc1	AGV01	go_to	19	failed	2026-06-05 14:18:20.852317+07	2026-06-05 14:18:20.85375+07	2026-06-05 14:18:21.113426+07	Không tìm được đường đi từ 181 -> 19	mq0le6av3h20z34kb1v	A06
1413	f68d4144	AGV01	go_charge	\N	completed	2026-06-04 09:54:59.423539+07	2026-06-04 09:55:46.047693+07	2026-06-04 09:55:55.556437+07		mpywjzsdg769egz5gc	A06
1414	dc8a08f4	AGV02	go_to	17	completed	2026-06-04 09:55:07.615886+07	2026-06-04 09:55:07.615886+07	2026-06-04 09:56:10.286839+07	lifecycle:picking:confirmed	mpywk6e380v4yuir3ck	A06
1437	325a1b02	AGV02	go_to	6	cancelled	2026-06-04 09:59:56.764347+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1438	fdc92479	AGV01	go_charge	\N	completed	2026-06-04 09:59:57.667261+07	2026-06-04 09:59:57.667261+07	2026-06-04 10:00:36.053065+07	charge_arrived	mpywqe73x7pi9rgvbg	Sạc Pin
1935	c4ecc9f6	AGV01	go_to	17	cancelled	2026-06-05 14:18:04.326328+07	\N	2026-06-05 14:19:41.169566+07	cancelled by user	mq0le6av3h20z34kb1v	A06
1489	b5a07295	AGV01	go_charge	\N	completed	2026-06-04 11:02:36.091884+07	2026-06-04 11:02:49.379759+07	2026-06-04 11:02:49.395741+07	bounce_wait	mpyytk00ckkmri4f5is	A06
1936	3bbcabfb	AGV01	go_charge	\N	cancelled	2026-06-05 14:18:04.34133+07	\N	2026-06-05 14:19:41.169566+07	cancelled by user	mq0le6av3h20z34kb1v	A06
1491	748ad0ad	AGV01	go_to	13	completed	2026-06-04 11:03:04.921431+07	2026-06-04 11:03:15.719716+07	2026-06-04 11:03:23.83159+07		\N	bounce_retry
1533	cc67de66	AGV02	go_charge	\N	completed	2026-06-05 08:25:37.706783+07	2026-06-05 08:25:50.492186+07	2026-06-05 08:26:27.877487+07	charge_arrived	mq08nen2vdfv577qq3	A06
1617	843ef55d	AGV01	go_charge	\N	completed	2026-06-05 09:44:51.111166+07	2026-06-05 09:44:51.111166+07	2026-06-05 09:44:51.746192+07	lifecycle:picking:confirmed	mq0bmtcxdm20h5q07b	Sạc Pin
1717	d6394420	AGV01	go_to	19	cancelled	2026-06-05 10:21:41.585104+07	\N	2026-06-05 10:26:02.510782+07	cancelled by user	mq0crn9jk7p1lcajwht	A05
1952	855e5cfe	AGV02	go_to	69	completed	2026-06-05 15:49:49.956608+07	2026-06-05 15:49:49.956608+07	2026-06-05 15:50:26.83338+07	lifecycle:picking:confirmed	mq0oo6lyz60r2fl53i	A06
1762	718ce573	AGV01	go_to	17	completed	2026-06-05 11:03:41.31536+07	2026-06-05 11:04:09.982028+07	2026-06-05 11:04:31.853671+07	lifecycle:picking:confirmed	mq0eg71h94k4md5ku4q	A06
1764	c20ccca9	AGV02	go_to	17	completed	2026-06-05 11:03:51.97685+07	2026-06-05 11:03:51.97685+07	2026-06-05 11:04:33.814567+07	lifecycle:picking:confirmed	mq0egfflzdstopdk6cd	A06
1763	e0eff922	AGV01	go_charge	\N	completed	2026-06-05 11:03:41.328364+07	2026-06-05 11:04:31.859673+07	2026-06-05 11:04:47.535822+07		mq0eg71h94k4md5ku4q	A06
1813	14946abd	AGV02	go_to	9	cancelled	2026-06-05 11:34:22.242958+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1887	f6dc42d5	AGV01	go_to	17	completed	2026-06-05 13:22:14.288303+07	2026-06-05 13:22:48.411272+07	2026-06-05 13:23:13.477957+07	lifecycle:picking:confirmed	mq0jed864yq1si1mtg	A06
1956	2d55d26d	AGV02	go_charge	14	cancelled	2026-06-05 15:51:36.198149+07	\N	2026-06-05 15:51:58.531201+07	cancelled by user	mq0oo6lyz60r2fl53i	A06
1894	74419728	AGV01	go_charge	\N	completed	2026-06-05 13:23:21.724024+07	2026-06-05 13:23:37.186315+07	2026-06-05 13:24:21.767952+07	charge_arrived	\N	bounce_retry
1973	8fb60ad9	AGV02	go_to	69	completed	2026-06-05 16:03:06.519049+07	2026-06-05 16:03:21.815975+07	2026-06-05 16:04:01.11602+07	lifecycle:picking:confirmed	mq0p443qs59j1txq17m	A02
1976	1b2864e0	AGV02	go_to	69	completed	2026-06-05 16:07:04.342459+07	2026-06-05 16:07:04.342459+07	2026-06-05 16:07:31.934648+07	lifecycle:picking:confirmed	mq0pacqsb8k14wijidp	A05
1994	ff4cfa8b	AGV02	go_to	69	completed	2026-06-05 17:02:08.671238+07	2026-06-05 17:02:08.671238+07	2026-06-05 17:02:39.120876+07	lifecycle:picking:confirmed	mq0r96dqvy8iyufp54	A06
2042	745ed01f	AGV02	go_to	69	completed	2026-06-06 11:28:00.203669+07	2026-06-06 11:28:15.051313+07	2026-06-06 11:29:05.691314+07	lifecycle:picking:confirmed	mq1uq1t87l733sq2g1u	A02
2004	259b81d8	AGV02	go_to	69	completed	2026-06-06 09:37:35.626521+07	2026-06-06 09:37:47.160818+07	2026-06-06 09:39:31.366006+07	lifecycle:picking:confirmed	mq1qrfmxrwxscfgmrf	A02
2021	e3e26b5a	AGV02	go_to	18	completed	2026-06-06 10:16:20.965145+07	2026-06-06 10:16:32.848303+07	2026-06-06 10:16:49.056865+07	lifecycle:picking:confirmed	mq1s6ka7y9ki2n4sych	A02
2031	52931ca6	AGV02	go_to	69	completed	2026-06-06 11:02:35.564181+07	2026-06-06 11:03:46.68971+07	2026-06-06 11:04:01.726675+07		mq1tum5wpi2jdka25ri	A02
2038	e53620cf	AGV02	go_to	19	completed	2026-06-06 11:27:02.023577+07	2026-06-06 11:27:31.822259+07	2026-06-06 11:27:47.51526+07	lifecycle:picking:confirmed	mq1uq1t87l733sq2g1u	A02
2033	8d709023	AGV02	go_to	69	cancelled	2026-06-06 11:03:46.930631+07	2026-06-06 11:04:01.727673+07	2026-06-06 11:06:44.210717+07	force-cancelled by user	mq1tum5wpi2jdka25ri	A02
2039	6f388a8f	AGV02	go_to	18	completed	2026-06-06 11:27:02.02858+07	2026-06-06 11:27:47.51526+07	2026-06-06 11:28:00.179703+07	lifecycle:picking:confirmed	mq1uq1t87l733sq2g1u	A02
2036	15b39430	AGV02	go_charge	\N	completed	2026-06-06 11:06:57.483245+07	2026-06-06 11:07:18.294457+07	2026-06-06 11:07:50.681338+07	charge_arrived	mq1u02s76ouo4yfrnlm	Sạc Pin
2044	b744c66c	AGV02	go_charge	\N	completed	2026-06-06 11:34:12.534388+07	2026-06-06 11:35:02.948599+07	2026-06-06 11:35:17.72579+07		f0b3a0fc	Lấy hàng
2043	09c6ed78	AGV02	go_to	17	completed	2026-06-06 11:34:12.23599+07	2026-06-06 11:34:12.23599+07	2026-06-06 11:34:41.078691+07	lifecycle:picking:confirmed	f0b3a0fc	Lấy hàng
2045	1206e294	AGV02	go_to	17	completed	2026-06-06 11:34:12.533367+07	2026-06-06 11:34:41.079691+07	2026-06-06 11:35:02.947602+07	lifecycle:picking:confirmed	f0b3a0fc	Lấy hàng
2046	1ee41dd9	AGV02	go_charge	\N	completed	2026-06-06 11:35:02.961608+07	2026-06-06 11:35:17.726741+07	2026-06-06 11:36:02.526578+07	charge_arrived	f0b3a0fc	Lấy hàng
2048	5a0b68bf	AGV02	go_to	19	completed	2026-06-06 11:45:06.085164+07	2026-06-06 11:45:36.305558+07	2026-06-06 11:45:55.722416+07	event:continue	mq1vdaav5z1ly3e7d5e	A02
2051	7aa66bc3	AGV02	go_to	69	completed	2026-06-06 11:45:06.090189+07	2026-06-06 11:46:16.400907+07	2026-06-06 11:46:35.723379+07		mq1vdaav5z1ly3e7d5e	A02
2050	148b46fc	AGV02	go_charge	\N	completed	2026-06-06 11:45:06.099187+07	2026-06-06 11:47:30.979309+07	2026-06-06 11:48:21.264118+07	charge_arrived	mq1vdaav5z1ly3e7d5e	A02
2783	7a7dbef5	AGV01	go_charge	\N	completed	2026-06-15 10:54:14.988313+07	2026-06-15 10:55:25.96534+07	2026-06-15 10:55:41.13447+07		mqeoijy2p8n8127dea	A06
515	5903e13a	AGV01	go_to	5	failed	2026-06-02 08:25:26.956522+07	2026-06-02 08:25:26.956522+07	2026-06-02 08:25:36.960205+07	dispatch failed	c2068c0348	Mô phỏng vòng 1/10
518	1730751b	AGV01	go_to	4	failed	2026-06-02 08:26:09.063573+07	\N	\N	\N	c2068c0348	Mô phỏng vòng 1/10
521	8a060dcf	AGV01	go_to	19	failed	2026-06-02 08:26:30.1138+07	\N	\N	\N	c2068c0348	Mô phỏng vòng 1/10
525	00268317	AGV01	go_to	2	failed	2026-06-02 08:27:12.367684+07	\N	\N	\N	c2068c0348	Mô phỏng vòng 2/10
526	9580657f	AGV01	go_to	3	failed	2026-06-02 08:27:23.397549+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 5/10
1259	059595b8	AGV02	go_to	17	running	2026-06-03 16:32:00.413925+07	\N	\N	\N	mpxvapspozh8dsfy79e	A06
1430	d89042d7	AGV02	go_to	7	cancelled	2026-06-04 09:58:58.554806+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1431	4b592ed6	AGV02	go_to	6	cancelled	2026-06-04 09:59:07.803668+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1257	9df05262	AGV01	go_to	17	completed	2026-06-03 16:31:46.695109+07	2026-06-03 16:32:16.490205+07	2026-06-03 16:32:33.620622+07	lifecycle:picking:confirmed	mpxvaf1rfcvmye8b5xg	A06
1258	9c7f9e3d	AGV01	go_charge	\N	completed	2026-06-03 16:31:46.708112+07	2026-06-03 16:32:33.621623+07	2026-06-03 16:32:38.858873+07		mpxvaf1rfcvmye8b5xg	A06
1263	e7dd45ed	AGV01	go_to	13	queued	2026-06-03 16:33:00.580714+07	\N	\N	\N	mpxvaf1rfcvmye8b5xg	A06
1264	d4f56c62	AGV01	go_to	9	queued	2026-06-03 16:33:07.59222+07	\N	\N	\N	mpxvaf1rfcvmye8b5xg	A06
1354	a87e9e3b	AGV02	go_to	17	running	2026-06-04 08:20:54.631382+07	\N	\N	\N	mpyt70ir6femvsia8z	A06
1429	504477c8	AGV02	go_to	6	cancelled	2026-06-04 09:58:51.534216+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1353	8a9f374f	AGV01	go_charge	\N	completed	2026-06-04 08:20:37.782743+07	2026-06-04 08:21:52.884388+07	2026-06-04 08:22:00.326173+07		mpyt6nghv885xz3tlho	A06
1358	0429a3b2	AGV01	go_to	13	queued	2026-06-04 08:22:19.97146+07	\N	\N	\N	mpyt6nghv885xz3tlho	A06
1359	f8cd269b	AGV01	go_to	9	queued	2026-06-04 08:22:26.967139+07	\N	\N	\N	mpyt6nghv885xz3tlho	A06
1432	8ed47ed9	AGV02	go_to	7	cancelled	2026-06-04 09:59:17.078789+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1412	673c7997	AGV01	go_to	17	completed	2026-06-04 09:54:59.406992+07	2026-06-04 09:55:26.495431+07	2026-06-04 09:55:46.047693+07	lifecycle:picking:confirmed	mpywjzsdg769egz5gc	A06
1415	6ac14c6b	AGV02	go_to	17	completed	2026-06-04 09:55:07.778523+07	2026-06-04 09:56:10.287874+07	2026-06-04 09:57:27.675091+07	lifecycle:picking:confirmed	mpywk6e380v4yuir3ck	A06
1493	30f26ca3	AGV01	go_to	96	cancelled	2026-06-04 14:48:29.293072+07	2026-06-04 14:48:29.293072+07	2026-06-04 14:48:53.766996+07	force-cancelled by user	mpz71fxaido334msx7	A06
1436	ec03d9d0	AGV02	go_to	7	cancelled	2026-06-04 09:59:47.443682+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1428	474656e8	AGV02	go_to	7	cancelled	2026-06-04 09:58:44.482781+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1416	448fd44a	AGV02	go_charge	\N	cancelled	2026-06-04 09:55:07.806546+07	2026-06-04 09:57:27.675091+07	2026-06-04 10:00:27.230112+07	force-cancelled by user	mpywk6e380v4yuir3ck	A06
1427	80d26265	AGV02	go_to	6	cancelled	2026-06-04 09:58:35.244977+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1426	a375590f	AGV02	go_to	7	cancelled	2026-06-04 09:58:26.018115+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1425	4488bfbc	AGV02	go_to	6	cancelled	2026-06-04 09:58:18.981126+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1423	305ca0aa	AGV02	go_to	6	cancelled	2026-06-04 09:58:04.845597+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1424	7d0b7bb5	AGV02	go_to	7	cancelled	2026-06-04 09:58:11.85587+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1422	230719c7	AGV02	go_to	7	cancelled	2026-06-04 09:57:57.803809+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1421	b6be91c7	AGV02	go_to	6	cancelled	2026-06-04 09:57:48.530945+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1420	8ba26b3c	AGV02	go_to	5	cancelled	2026-06-04 09:57:41.534376+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1419	6c5b12df	AGV02	go_charge	\N	cancelled	2026-06-04 09:57:27.696615+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1435	d6a74fdf	AGV02	go_to	6	cancelled	2026-06-04 09:59:38.155692+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1434	bfada081	AGV02	go_to	7	cancelled	2026-06-04 09:59:31.159696+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1433	9ad32f18	AGV02	go_to	6	cancelled	2026-06-04 09:59:24.089568+07	\N	2026-06-04 10:00:27.231113+07	cancelled by user	mpywk6e380v4yuir3ck	A06
1534	ed1c34c8	AGV01	go_to	17	completed	2026-06-05 08:38:04.713054+07	2026-06-05 08:38:04.713054+07	2026-06-05 08:38:37.517621+07	lifecycle:picking:confirmed	mq098xzwn77msiqfgf	A06
1537	57cedef4	AGV02	go_to	17	completed	2026-06-05 08:38:21.50947+07	2026-06-05 08:38:21.50947+07	2026-06-05 08:38:54.886491+07	lifecycle:picking:confirmed	mq099ayjde5badbj72o	A06
1536	98c18f28	AGV01	go_charge	\N	completed	2026-06-05 08:38:04.928618+07	2026-06-05 08:38:58.784584+07	2026-06-05 08:39:10.090037+07		mq098xzwn77msiqfgf	A06
1722	4dddbf89	AGV02	go_to	64	completed	2026-06-05 10:28:15.018834+07	2026-06-05 10:28:31.412629+07	2026-06-05 10:28:47.396088+07		mq0ctlkpihg5smkt3yo	A06
1544	86bd7b44	AGV01	go_charge	\N	cancelled	2026-06-05 08:42:12.464031+07	2026-06-05 08:42:19.902999+07	2026-06-05 08:44:22.272098+07	force-cancelled by user	mq09dsisge3y30xhymu	A06
1618	16c26c55	AGV01	go_charge	\N	completed	2026-06-05 09:44:51.129633+07	2026-06-05 09:44:51.747177+07	2026-06-05 09:45:07.570442+07		mq0bmtcxdm20h5q07b	Sạc Pin
1769	02938d32	AGV01	go_to	9	completed	2026-06-05 11:05:14.5278+07	2026-06-05 11:10:30.469632+07	2026-06-05 11:11:05.074671+07	lifecycle:picking:confirmed	mq0eg71h94k4md5ku4q	A06
1724	2243ee70	AGV02	go_to	64	completed	2026-06-05 10:28:47.462973+07	2026-06-05 10:28:50.653756+07	2026-06-05 10:29:27.02392+07	lifecycle:picking:confirmed	mq0ctlkpihg5smkt3yo	A06
1721	3e6782dc	AGV02	go_to	19	cancelled	2026-06-05 10:28:05.200138+07	2026-06-05 10:29:41.796401+07	2026-06-05 10:29:52.853128+07	force-cancelled by user	mq0ctlkpihg5smkt3yo	A06
1720	4417ff5a	AGV02	go_to	64	cancelled	2026-06-05 10:27:57.925425+07	\N	2026-06-05 10:29:52.853128+07	cancelled by user	mq0ctlkpihg5smkt3yo	A06
1719	9863e54c	AGV02	go_to	19	cancelled	2026-06-05 10:27:50.950854+07	\N	2026-06-05 10:29:52.853128+07	cancelled by user	mq0ctlkpihg5smkt3yo	A06
1718	96b79649	AGV02	go_to	16	cancelled	2026-06-05 10:27:43.991248+07	\N	2026-06-05 10:29:52.853128+07	cancelled by user	mq0ctlkpihg5smkt3yo	A06
1770	a50eadfc	AGV02	go_charge	\N	cancelled	2026-06-05 11:09:48.801451+07	2026-06-05 11:09:48.801451+07	2026-06-05 11:09:59.339659+07	force-cancelled by user	mq0eo2r913uge1eiaqfp	Sạc Pin
1767	b5b52e4d	AGV01	go_charge	\N	completed	2026-06-05 11:04:32.104859+07	2026-06-05 11:04:47.53633+07	2026-06-05 11:10:30.46865+07		mq0eg71h94k4md5ku4q	A06
1893	f6bb21fa	AGV01	go_charge	\N	completed	2026-06-05 13:23:21.71202+07	2026-06-05 13:23:21.71202+07	2026-06-05 13:23:37.186315+07		\N	bounce_retry
1768	fbec31ce	AGV01	go_to	13	cancelled	2026-06-05 11:05:07.366926+07	\N	2026-06-05 11:11:11.435965+07	cancelled by user	mq0eg71h94k4md5ku4q	A06
1844	e900f22b	AGV01	go_to	7	cancelled	2026-06-05 11:36:27.991279+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1895	ce5d28ac	AGV02	go_charge	\N	completed	2026-06-05 13:25:44.698851+07	2026-06-05 13:25:44.697836+07	2026-06-05 13:25:58.757473+07		mq0jivw60q1pqi31pmn	Sạc Pin
1896	971dbd20	AGV02	go_charge	\N	completed	2026-06-05 13:25:44.827392+07	2026-06-05 13:25:58.759437+07	2026-06-05 13:26:59.072913+07	charge_arrived	mq0jivw60q1pqi31pmn	Sạc Pin
1938	48dfb23d	AGV02	go_to	69	completed	2026-06-05 14:36:30.232808+07	2026-06-05 14:36:30.232808+07	2026-06-05 14:36:57.605484+07	lifecycle:picking:confirmed	mq0m1vq5hmrmfui3rn	A06
1953	0577d232	AGV02	go_to	69	completed	2026-06-05 15:49:50.014252+07	2026-06-05 15:50:26.83338+07	2026-06-05 15:50:42.363019+07		mq0oo6lyz60r2fl53i	A06
1954	c37485ec	AGV02	go_charge	\N	cancelled	2026-06-05 15:49:50.0303+07	2026-06-05 15:51:11.319182+07	2026-06-05 15:51:58.529674+07	force-cancelled by user	mq0oo6lyz60r2fl53i	A06
519	518b3d6f	AGV01	go_to	3	failed	2026-06-02 08:25:59.04256+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 4/10
524	d2b7c99c	AGV01	go_to	2	failed	2026-06-02 08:27:02.344393+07	\N	\N	\N	79087a1c35	Mô phỏng vòng 5/10
532	afb68b0a	AGV01	go_to	2	cancelled	2026-06-02 08:29:50.164604+07	2026-06-02 08:29:50.164604+07	2026-06-02 08:30:13.798328+07	force-cancelled by user	ae4269f1cc	Mô phỏng vòng 1/10
533	ae12157c	AGV01	go_to	2	running	2026-06-02 08:38:59.055542+07	\N	\N	\N	1d96ea3cb0	Mô phỏng vòng 1/10
534	07657b37	AGV01	go_to	2	running	2026-06-02 08:45:01.634185+07	\N	\N	\N	164024c1b8	Mô phỏng vòng 1/10
536	8172ce6a	AGV01	go_to	3	running	2026-06-02 08:59:12.886517+07	\N	\N	\N	1b38308da8	Mô phỏng vòng 1/10
535	e23a1de4	AGV01	go_to	2	completed	2026-06-02 08:59:04.375064+07	2026-06-02 08:59:04.375064+07	2026-06-02 08:59:12.885512+07	sim:auto_confirm	1b38308da8	Mô phỏng vòng 1/10
537	2f5313ae	AGV01	go_to	2	completed	2026-06-02 09:07:57.550248+07	2026-06-02 09:07:57.550248+07	2026-06-02 09:08:05.745365+07	sim:auto_confirm	40f64d574d	Mô phỏng vòng 1/10
538	c0c98cdd	AGV01	go_to	3	cancelled	2026-06-02 09:08:05.748342+07	2026-06-02 09:08:05.748342+07	2026-06-02 09:08:12.69051+07	force-cancelled by user	40f64d574d	Mô phỏng vòng 1/10
539	08f00254	AGV01	go_to	2	failed	2026-06-02 09:13:57.655574+07	2026-06-02 09:13:57.655574+07	2026-06-02 09:13:57.73471+07	local variable '_is_sim_agv' referenced before assignment	6d50b095c1	Mô phỏng vòng 1/10
540	b45a5fcf	AGV01	go_to	2	failed	2026-06-02 09:13:59.738258+07	2026-06-02 09:13:59.738258+07	2026-06-02 09:13:59.885474+07	local variable '_is_sim_agv' referenced before assignment	6d50b095c1	Mô phỏng vòng 1/10
541	1f773bb0	AGV01	go_to	2	failed	2026-06-02 09:14:01.911097+07	2026-06-02 09:14:01.911097+07	2026-06-02 09:14:01.945104+07	local variable '_is_sim_agv' referenced before assignment	6d50b095c1	Mô phỏng vòng 1/10
542	c6ccea72	AGV01	go_to	2	failed	2026-06-02 09:14:03.975393+07	2026-06-02 09:14:03.975393+07	2026-06-02 09:14:04.037966+07	local variable '_is_sim_agv' referenced before assignment	6d50b095c1	Mô phỏng vòng 1/10
543	30505a84	AGV01	go_to	2	failed	2026-06-02 09:14:06.046496+07	2026-06-02 09:14:06.046496+07	2026-06-02 09:14:06.074028+07	local variable '_is_sim_agv' referenced before assignment	6d50b095c1	Mô phỏng vòng 1/10
544	b88651fa	AGV01	go_to	2	failed	2026-06-02 09:14:08.096989+07	2026-06-02 09:14:08.096989+07	2026-06-02 09:14:08.115458+07	local variable '_is_sim_agv' referenced before assignment	6d50b095c1	Mô phỏng vòng 1/10
545	fc92b7b2	AGV01	go_to	2	failed	2026-06-02 09:14:10.125152+07	2026-06-02 09:14:10.125152+07	2026-06-02 09:14:10.145669+07	local variable '_is_sim_agv' referenced before assignment	6d50b095c1	Mô phỏng vòng 1/10
546	8776db6d	AGV01	go_to	2	failed	2026-06-02 09:14:12.148385+07	2026-06-02 09:14:12.148385+07	2026-06-02 09:14:12.159334+07	local variable '_is_sim_agv' referenced before assignment	6d50b095c1	Mô phỏng vòng 1/10
547	1e687347	AGV01	go_to	2	failed	2026-06-02 09:14:14.163558+07	2026-06-02 09:14:14.163558+07	2026-06-02 09:14:14.175703+07	local variable '_is_sim_agv' referenced before assignment	6d50b095c1	Mô phỏng vòng 1/10
548	121be910	AGV01	go_to	2	failed	2026-06-02 09:14:16.183667+07	2026-06-02 09:14:16.183667+07	2026-06-02 09:14:16.195657+07	local variable '_is_sim_agv' referenced before assignment	6d50b095c1	Mô phỏng vòng 1/10
549	f8c6fa25	AGV01	go_to	2	failed	2026-06-02 09:14:18.20511+07	2026-06-02 09:14:18.20511+07	2026-06-02 09:14:18.221126+07	local variable '_is_sim_agv' referenced before assignment	6d50b095c1	Mô phỏng vòng 1/10
550	017af2a4	AGV01	go_to	2	failed	2026-06-02 09:14:20.247633+07	2026-06-02 09:14:20.247633+07	2026-06-02 09:14:20.254629+07	local variable '_is_sim_agv' referenced before assignment	6d50b095c1	Mô phỏng vòng 1/10
551	71656512	AGV01	go_to	2	failed	2026-06-02 09:14:22.259184+07	2026-06-02 09:14:22.259184+07	2026-06-02 09:14:22.277487+07	local variable '_is_sim_agv' referenced before assignment	6d50b095c1	Mô phỏng vòng 1/10
552	17413e57	AGV01	go_to	2	failed	2026-06-02 09:14:24.302477+07	2026-06-02 09:14:24.302477+07	2026-06-02 09:14:24.318476+07	local variable '_is_sim_agv' referenced before assignment	6d50b095c1	Mô phỏng vòng 1/10
553	5442671b	AGV01	go_to	2	cancelled	2026-06-02 09:19:04.571593+07	2026-06-02 09:19:04.571593+07	2026-06-02 09:19:21.386547+07	force-cancelled by user	6bc1f7b0e4	Mô phỏng vòng 1/10
554	b9e2207b	AGV01	go_to	2	running	2026-06-02 09:22:21.94253+07	\N	\N	\N	32b3543671	Mô phỏng vòng 1/10
555	dcbec546	AGV01	go_to	18	completed	2026-06-02 09:29:57.08727+07	2026-06-02 09:29:57.08727+07	2026-06-02 09:30:26.541301+07	lifecycle:picking:confirmed	mpw0s3hpjqvcg15x8on	A06
557	242a096f	AGV01	go_charge	\N	completed	2026-06-02 09:29:57.186968+07	2026-06-02 09:30:40.549861+07	2026-06-02 09:30:45.803636+07		mpw0s3hpjqvcg15x8on	A06
566	7c7a82a2	AGV01	go_to	4	completed	2026-06-02 09:54:38.979564+07	2026-06-02 09:54:38.979564+07	2026-06-02 09:55:08.832985+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 1/10
556	8aecbe08	AGV01	go_to	18	completed	2026-06-02 09:29:57.164811+07	2026-06-02 09:30:26.542302+07	2026-06-02 09:30:40.548872+07	lifecycle:picking:confirmed	mpw0s3hpjqvcg15x8on	A06
558	ab0b19be	AGV01	go_charge	\N	completed	2026-06-02 09:30:40.62796+07	2026-06-02 09:30:45.806976+07	2026-06-02 09:31:49.800991+07	charge_arrived	mpw0s3hpjqvcg15x8on	A06
559	9d5212f2	AGV01	go_to	18	completed	2026-06-02 09:32:46.053573+07	2026-06-02 09:32:46.053573+07	2026-06-02 09:33:16.52907+07	lifecycle:picking:confirmed	mpw0vpwd92cw2thrrva	A06
567	36d3b333	AGV01	go_to	4	completed	2026-06-02 09:54:39.030949+07	2026-06-02 09:55:08.833976+07	2026-06-02 09:55:17.938746+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 1/10
560	38dea3d5	AGV01	go_to	18	completed	2026-06-02 09:32:46.083594+07	2026-06-02 09:33:16.531097+07	2026-06-02 09:33:30.387602+07	lifecycle:picking:confirmed	mpw0vpwd92cw2thrrva	A06
561	bae368fd	AGV01	go_charge	\N	completed	2026-06-02 09:32:46.10646+07	2026-06-02 09:33:30.387602+07	2026-06-02 09:33:36.182813+07		mpw0vpwd92cw2thrrva	A06
568	5012baa6	AGV01	go_to	1	completed	2026-06-02 09:55:18.002466+07	2026-06-02 09:55:18.002466+07	2026-06-02 09:55:26.625228+07		064a9bb2ef	Mô phỏng vòng 1/10
562	9564b4b2	AGV01	go_charge	\N	completed	2026-06-02 09:33:30.693324+07	2026-06-02 09:33:36.183806+07	2026-06-02 09:34:11.938116+07	charge_arrived	mpw0vpwd92cw2thrrva	A06
564	b4748e07	AGV01	go_to	2	running	2026-06-02 09:36:02.897554+07	\N	\N	\N	412b9c32ff	Mô phỏng vòng 1/10
563	e24595a5	AGV01	go_to	1	completed	2026-06-02 09:35:50.804998+07	2026-06-02 09:35:50.804998+07	2026-06-02 09:36:02.895067+07	sim:auto_confirm	412b9c32ff	Mô phỏng vòng 1/10
565	539e0f8e	AGV01	go_to	3	queued	2026-06-02 09:46:03.116678+07	\N	\N	\N	412b9c32ff	Mô phỏng vòng 1/10
570	f44c6313	AGV01	go_to	4	completed	2026-06-02 09:55:48.525889+07	2026-06-02 09:55:48.525889+07	2026-06-02 09:56:06.850509+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 2/10
574	3a5f6bc7	AGV01	go_to	4	completed	2026-06-02 09:56:44.388887+07	2026-06-02 09:56:44.388887+07	2026-06-02 09:57:02.212256+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 3/10
569	72ec7d37	AGV01	go_to	1	completed	2026-06-02 09:55:18.132547+07	2026-06-02 09:55:26.626292+07	2026-06-02 09:55:48.522882+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 1/10
571	c9a2dea0	AGV01	go_to	4	completed	2026-06-02 09:55:48.547884+07	2026-06-02 09:56:06.851508+07	2026-06-02 09:56:15.933684+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 2/10
572	58c2174f	AGV01	go_to	1	completed	2026-06-02 09:56:15.936635+07	2026-06-02 09:56:15.936635+07	2026-06-02 09:56:24.484864+07		064a9bb2ef	Mô phỏng vòng 2/10
573	2d9d97bc	AGV01	go_to	1	completed	2026-06-02 09:56:15.956662+07	2026-06-02 09:56:24.485859+07	2026-06-02 09:56:44.384886+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 2/10
576	4a4f164c	AGV01	go_to	1	completed	2026-06-02 09:57:11.312733+07	2026-06-02 09:57:11.312733+07	2026-06-02 09:57:19.697128+07		064a9bb2ef	Mô phỏng vòng 3/10
575	b599b820	AGV01	go_to	4	completed	2026-06-02 09:56:44.417448+07	2026-06-02 09:57:02.212256+07	2026-06-02 09:57:11.310307+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 3/10
578	38045e49	AGV01	go_to	4	completed	2026-06-02 09:57:39.767564+07	2026-06-02 09:57:39.767564+07	2026-06-02 09:57:57.996621+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 4/10
577	264b6d38	AGV01	go_to	1	completed	2026-06-02 09:57:11.359347+07	2026-06-02 09:57:19.698132+07	2026-06-02 09:57:39.766561+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 3/10
580	41afd238	AGV01	go_to	1	completed	2026-06-02 09:58:07.107314+07	2026-06-02 09:58:07.107314+07	2026-06-02 09:58:15.506499+07		064a9bb2ef	Mô phỏng vòng 4/10
579	2ae4825c	AGV01	go_to	4	completed	2026-06-02 09:57:39.785562+07	2026-06-02 09:57:57.997529+07	2026-06-02 09:58:07.105319+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 4/10
581	ddbfe7bb	AGV01	go_to	1	completed	2026-06-02 09:58:07.16487+07	2026-06-02 09:58:15.5075+07	2026-06-02 09:58:35.473826+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 4/10
583	38b37c5e	AGV01	go_to	4	completed	2026-06-02 09:58:35.579023+07	2026-06-02 09:58:53.847508+07	2026-06-02 09:59:02.493669+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 5/10
1267	479ab429	AGV02	go_to	3	cancelled	2026-06-03 16:37:42.898501+07	\N	2026-06-03 16:37:45.975798+07	cancelled by user	mpxvhwndj6bjibw4k9b	Sạc Pin
585	273d416b	AGV01	go_to	1	completed	2026-06-02 09:59:02.539493+07	2026-06-02 09:59:11.017306+07	2026-06-02 09:59:31.485369+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 5/10
1265	b011716c	AGV02	go_charge	\N	cancelled	2026-06-03 16:37:35.886892+07	2026-06-03 16:37:35.886892+07	2026-06-03 16:37:45.975798+07	force-cancelled by user	mpxvhwndj6bjibw4k9b	Sạc Pin
591	726aab3f	AGV01	go_to	4	completed	2026-06-02 10:00:27.388914+07	2026-06-02 10:00:45.659309+07	2026-06-02 10:00:54.761781+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 7/10
592	d43b2170	AGV01	go_to	1	completed	2026-06-02 10:00:54.763763+07	2026-06-02 10:00:54.763763+07	2026-06-02 10:01:03.323356+07		064a9bb2ef	Mô phỏng vòng 7/10
1266	03cb29e8	AGV02	go_charge	\N	cancelled	2026-06-03 16:37:36.074804+07	\N	2026-06-03 16:37:45.975798+07	cancelled by user	mpxvhwndj6bjibw4k9b	Sạc Pin
597	b9337f0d	AGV01	go_to	1	completed	2026-06-02 10:01:50.668872+07	2026-06-02 10:01:59.16138+07	2026-06-02 10:02:19.105001+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 8/10
1897	fb657765	AGV01	go_to	17	completed	2026-06-05 13:42:43.124501+07	2026-06-05 13:42:43.124501+07	2026-06-05 13:43:18.644162+07	lifecycle:picking:confirmed	mq0k4ppkidezjwnyep	A06
1269	4dda2e98	AGV01	go_charge	\N	cancelled	2026-06-03 16:38:23.474269+07	2026-06-03 16:38:28.6813+07	2026-06-03 16:39:06.02376+07	force-cancelled by user	mpxvixcxqkvk21nns9i	Sạc Pin
1360	955d979b	AGV01	go_charge	\N	completed	2026-06-04 08:30:09.974531+07	2026-06-04 08:30:09.974531+07	2026-06-04 08:31:10.093796+07	charge_arrived	mpytix0ry08k9qs6cgd	Sạc Pin
1417	c3ed4555	AGV01	go_charge	\N	cancelled	2026-06-04 09:55:46.35754+07	2026-06-04 09:55:55.556437+07	2026-06-04 09:59:52.766472+07	force-cancelled by user	mpywjzsdg769egz5gc	A06
1418	18c22063	AGV01	go_charge	\N	cancelled	2026-06-04 09:56:29.057222+07	\N	2026-06-04 09:59:52.766472+07	cancelled by user	\N	bounce_retry
1494	d33494d9	AGV01	go_charge	\N	cancelled	2026-06-04 14:48:29.51732+07	\N	2026-06-04 14:48:53.766996+07	cancelled by user	mpz71fxaido334msx7	A06
1535	18d84a27	AGV01	go_to	17	completed	2026-06-05 08:38:04.917609+07	2026-06-05 08:38:37.518623+07	2026-06-05 08:38:58.783534+07	lifecycle:picking:confirmed	mq098xzwn77msiqfgf	A06
1538	a7f2cc20	AGV02	go_to	17	completed	2026-06-05 08:38:21.524468+07	2026-06-05 08:38:54.886491+07	2026-06-05 08:40:00.880245+07	lifecycle:picking:confirmed	mq099ayjde5badbj72o	A06
2005	78f2f81a	AGV02	go_to	96	completed	2026-06-06 09:50:30.130284+07	2026-06-06 09:50:30.130284+07	2026-06-06 09:50:58.3317+07	lifecycle:picking:confirmed	mq1r9xlxijx6nobimq	A02
1540	edcf22cc	AGV02	go_to	17	completed	2026-06-05 08:38:54.899498+07	2026-06-05 08:40:00.880245+07	2026-06-05 08:41:31.638074+07	lifecycle:picking:confirmed	mq099ayjde5badbj72o	A06
1905	a61777e3	AGV01	go_charge	\N	completed	2026-06-05 13:43:44.408918+07	2026-06-05 13:43:59.936331+07	2026-06-05 13:44:50.882577+07	charge_arrived	\N	bounce_retry
1539	13a1c89b	AGV02	go_charge	\N	completed	2026-06-05 08:38:21.537475+07	2026-06-05 08:41:31.643071+07	2026-06-05 08:42:07.118554+07	charge_arrived	mq099ayjde5badbj72o	A06
1542	e3e85306	AGV01	go_to	96	completed	2026-06-05 08:41:50.89078+07	2026-06-05 08:41:50.89078+07	2026-06-05 08:42:12.44149+07	lifecycle:picking:confirmed	mq09dsisge3y30xhymu	A06
1901	f63b01cd	AGV02	go_to	17	cancelled	2026-06-05 13:42:59.437769+07	2026-06-05 13:43:34.56047+07	2026-06-05 13:48:50.856967+07	force-cancelled by user	mq0k525lckpydkmtaes	A06
1543	be61f586	AGV01	go_charge	\N	completed	2026-06-05 08:41:50.935131+07	2026-06-05 08:42:12.44149+07	2026-06-05 08:42:19.90201+07		mq09dsisge3y30xhymu	A06
1902	530f7aea	AGV02	go_charge	\N	cancelled	2026-06-05 13:42:59.445767+07	\N	2026-06-05 13:48:50.856967+07	cancelled by user	mq0k525lckpydkmtaes	A06
1619	b38fa9ac	AGV01	go_charge	\N	completed	2026-06-05 09:44:51.781192+07	2026-06-05 09:45:07.571315+07	2026-06-05 09:45:35.361025+07	charge_arrived	mq0bmtcxdm20h5q07b	Sạc Pin
1903	9109a4b8	AGV02	go_to	17	cancelled	2026-06-05 13:43:34.573421+07	\N	2026-06-05 13:48:50.856967+07	cancelled by user	mq0k525lckpydkmtaes	A06
1723	9811a60f	AGV02	go_to	64	completed	2026-06-05 10:28:31.486201+07	2026-06-05 10:28:47.398092+07	2026-06-05 10:28:50.652756+07	event:continue	mq0ctlkpihg5smkt3yo	A06
1725	e406ac4e	AGV02	go_to	64	completed	2026-06-05 10:28:50.71386+07	2026-06-05 10:29:27.027937+07	2026-06-05 10:29:41.796401+07	lifecycle:picking:confirmed	mq0ctlkpihg5smkt3yo	A06
1772	30bbf909	AGV02	go_to	64	cancelled	2026-06-05 11:09:57.570532+07	\N	2026-06-05 11:09:59.340658+07	cancelled by user	mq0eo2r913uge1eiaqfp	Sạc Pin
1771	97a91e58	AGV02	go_charge	\N	cancelled	2026-06-05 11:09:49.00809+07	\N	2026-06-05 11:09:59.340658+07	cancelled by user	mq0eo2r913uge1eiaqfp	Sạc Pin
1773	c032ed29	AGV01	go_to	9	cancelled	2026-06-05 11:10:30.491019+07	2026-06-05 11:11:05.079686+07	2026-06-05 11:11:11.435965+07	force-cancelled by user	mq0eg71h94k4md5ku4q	A06
1839	e8d54580	AGV01	go_to	7	cancelled	2026-06-05 11:36:11.093808+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1939	1a9c16a6	AGV02	go_charge	\N	completed	2026-06-05 14:36:30.28338+07	2026-06-05 14:36:57.611488+07	2026-06-05 14:37:13.200894+07		mq0m1vq5hmrmfui3rn	A06
1955	6d6c88ce	AGV02	go_to	69	completed	2026-06-05 15:50:27.102674+07	2026-06-05 15:50:42.368+07	2026-06-05 15:51:11.319182+07	lifecycle:picking:confirmed	mq0oo6lyz60r2fl53i	A06
2006	c4f63c6d	AGV02	go_to	96	completed	2026-06-06 09:50:30.322365+07	2026-06-06 09:50:58.3397+07	2026-06-06 09:51:13.829121+07		mq1r9xlxijx6nobimq	A02
1985	3c57c738	AGV02	go_to	96	completed	2026-06-05 16:09:10.380498+07	2026-06-05 16:09:25.630081+07	2026-06-05 16:09:42.262099+07	lifecycle:picking:confirmed	mq0pacqsb8k14wijidp	A05
2009	0c3603d2	AGV02	go_to	96	completed	2026-06-06 09:50:58.537583+07	2026-06-06 09:51:13.830114+07	2026-06-06 09:51:30.442767+07	lifecycle:picking:confirmed	mq1r9xlxijx6nobimq	A02
1995	e0f9fb73	AGV02	go_to	69	completed	2026-06-05 17:02:08.734056+07	2026-06-05 17:02:39.121879+07	2026-06-05 17:02:54.703619+07		mq0r96dqvy8iyufp54	A06
1997	49140894	AGV02	go_to	69	completed	2026-06-05 17:02:39.298128+07	2026-06-05 17:02:54.704615+07	2026-06-05 17:17:40.348459+07	lifecycle:picking:confirmed	mq0r96dqvy8iyufp54	A06
2007	2808a224	AGV02	go_to	69	completed	2026-06-06 09:50:30.339363+07	2026-06-06 09:51:30.442767+07	2026-06-06 09:52:04.505898+07	lifecycle:picking:confirmed	mq1r9xlxijx6nobimq	A02
1996	55f09dbf	AGV02	go_charge	\N	completed	2026-06-05 17:02:08.751371+07	2026-06-05 17:17:40.348459+07	2026-06-05 17:18:26.447382+07	charge_arrived	mq0r96dqvy8iyufp54	A06
2010	8a212711	AGV02	go_charge	\N	completed	2026-06-06 09:52:04.525904+07	2026-06-06 09:52:17.850572+07	2026-06-06 09:53:03.0955+07	charge_arrived	mq1r9xlxijx6nobimq	A02
2013	3f2bb5dd	AGV01	go_to	69	completed	2026-06-06 09:53:12.81192+07	2026-06-06 09:54:08.028488+07	2026-06-06 09:54:23.689421+07		mq1rdf47fxabgdfeun	A02
2012	87e0a60e	AGV01	go_to	18	completed	2026-06-06 09:53:12.793921+07	2026-06-06 09:53:46.378305+07	2026-06-06 09:54:08.028488+07	lifecycle:picking:confirmed	mq1rdf47fxabgdfeun	A02
2016	a6db137e	AGV01	go_to	69	completed	2026-06-06 09:54:23.69619+07	2026-06-06 09:55:17.206639+07	2026-06-06 09:55:54.384695+07	lifecycle:picking:confirmed	mq1rdf47fxabgdfeun	A02
2032	e06502d1	AGV02	go_charge	\N	cancelled	2026-06-06 11:02:35.570203+07	\N	2026-06-06 11:06:44.210717+07	cancelled by user	mq1tum5wpi2jdka25ri	A02
2015	33b6ff4e	AGV01	go_to	69	completed	2026-06-06 09:54:08.050864+07	2026-06-06 09:54:23.690455+07	2026-06-06 09:55:17.206639+07	lifecycle:picking:confirmed	mq1rdf47fxabgdfeun	A02
2022	305625c2	AGV02	go_to	64	running	2026-06-06 10:16:21.393+07	2026-06-06 10:16:32.842321+07	\N		mq1s6ka7y9ki2n4sych	A02
2014	21cb60e5	AGV01	go_charge	\N	cancelled	2026-06-06 09:53:12.818919+07	2026-06-06 09:55:54.384695+07	2026-06-06 09:56:42.662095+07	force-cancelled by user	mq1rdf47fxabgdfeun	A02
2027	97728ed9	AGV02	go_charge	\N	completed	2026-06-06 10:55:53.666936+07	2026-06-06 10:56:10.38778+07	2026-06-06 10:56:39.654579+07	charge_arrived	mq1tlrpbms7dzt5ulaf	Sạc Pin
2034	a3089418	AGV02	go_charge	\N	completed	2026-06-06 11:06:50.136221+07	2026-06-06 11:06:50.135219+07	2026-06-06 11:06:57.469137+07	off_route	mq1u02s76ouo4yfrnlm	Sạc Pin
2037	d90b9f60	AGV02	go_to	64	completed	2026-06-06 11:27:01.971045+07	2026-06-06 11:27:01.971045+07	2026-06-06 11:27:31.822259+07	lifecycle:picking:confirmed	mq1uq1t87l733sq2g1u	A02
2040	031a6874	AGV02	go_to	69	completed	2026-06-06 11:27:02.031102+07	2026-06-06 11:28:00.179703+07	2026-06-06 11:28:15.05032+07		mq1uq1t87l733sq2g1u	A02
2041	1312eb7d	AGV02	go_charge	\N	completed	2026-06-06 11:27:02.034096+07	2026-06-06 11:29:05.701322+07	2026-06-06 11:29:56.215348+07	charge_arrived	mq1uq1t87l733sq2g1u	A02
582	3ad2cbab	AGV01	go_to	4	completed	2026-06-02 09:58:35.475722+07	2026-06-02 09:58:35.475722+07	2026-06-02 09:58:53.846124+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 5/10
584	c5a6ce2c	AGV01	go_to	1	completed	2026-06-02 09:59:02.49662+07	2026-06-02 09:59:02.49662+07	2026-06-02 09:59:11.010382+07		064a9bb2ef	Mô phỏng vòng 5/10
586	3b642371	AGV01	go_to	4	completed	2026-06-02 09:59:31.516975+07	2026-06-02 09:59:31.516975+07	2026-06-02 09:59:49.831634+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 6/10
588	9ff9d807	AGV01	go_to	1	completed	2026-06-02 09:59:58.527963+07	2026-06-02 09:59:58.527963+07	2026-06-02 10:00:07.15792+07		064a9bb2ef	Mô phỏng vòng 6/10
590	9cb3c3c7	AGV01	go_to	4	completed	2026-06-02 10:00:27.302348+07	2026-06-02 10:00:27.302348+07	2026-06-02 10:00:45.649306+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 7/10
594	c5630b7b	AGV01	go_to	4	completed	2026-06-02 10:01:23.216386+07	2026-06-02 10:01:23.216386+07	2026-06-02 10:01:41.524144+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 8/10
596	eef40221	AGV01	go_to	1	completed	2026-06-02 10:01:50.657866+07	2026-06-02 10:01:50.657866+07	2026-06-02 10:01:59.160378+07		064a9bb2ef	Mô phỏng vòng 8/10
1268	440e9bc5	AGV01	go_charge	\N	completed	2026-06-03 16:38:23.463272+07	2026-06-03 16:38:23.463272+07	2026-06-03 16:38:28.680298+07		mpxvixcxqkvk21nns9i	Sạc Pin
1361	6408d7c9	AGV01	go_to	17	completed	2026-06-04 08:49:48.445053+07	2026-06-04 08:49:48.445053+07	2026-06-04 08:50:41.891271+07	lifecycle:picking:confirmed	mpyu86axx7lzlysmqp	A06
1637	a07c6176	AGV02	go_to	64	cancelled	2026-06-05 09:49:05.801977+07	\N	2026-06-05 09:50:15.931243+07	cancelled by user	mq0boupdx7iwru9r66	A06
1367	71e0e1ce	AGV01	go_charge	\N	completed	2026-06-04 08:51:05.559851+07	2026-06-04 08:51:13.82429+07	2026-06-04 08:51:20.958022+07		mpyu86axx7lzlysmqp	A06
1635	86c3ceb2	AGV02	go_to	9	cancelled	2026-06-05 09:48:58.705566+07	\N	2026-06-05 09:50:15.931243+07	cancelled by user	mq0boupdx7iwru9r66	A06
1365	5fca57d8	AGV02	go_to	17	completed	2026-06-04 08:50:04.455823+07	2026-06-04 08:51:21.293722+07	2026-06-04 08:52:16.787284+07		mpyu8io0o7n99j15qi	A06
1366	c71498da	AGV02	go_charge	\N	cancelled	2026-06-04 08:50:04.473788+07	\N	2026-06-04 08:54:37.359864+07	cancelled by user	mpyu8io0o7n99j15qi	A06
1439	2027b17b	AGV02	go_charge	\N	completed	2026-06-04 10:00:34.964867+07	2026-06-04 10:00:34.964867+07	2026-06-04 10:00:41.469459+07		mpywr6z2dnnf54l83c	Sạc Pin
1441	24e2ad18	AGV02	go_charge	\N	cancelled	2026-06-04 10:01:17.100013+07	2026-06-04 10:01:17.100013+07	2026-06-04 10:01:25.679112+07	force-cancelled by user	mpyws3hi53owkhe8075	Sạc Pin
1495	90636f7a	AGV01	go_to	69	cancelled	2026-06-04 14:54:22.777925+07	2026-06-04 14:54:22.777925+07	2026-06-04 15:15:24.324788+07	force-cancelled by user	mpz790of70twsdxqk6	A06
1631	920ccba4	AGV02	go_to	64	cancelled	2026-06-05 09:48:38.321341+07	\N	2026-06-05 09:50:15.931243+07	cancelled by user	mq0boupdx7iwru9r66	A06
1541	2661cc13	AGV01	go_charge	\N	completed	2026-06-05 08:38:58.808536+07	2026-06-05 08:39:10.090037+07	2026-06-05 08:39:50.896012+07	charge_arrived	mq098xzwn77msiqfgf	A06
1545	cf869d38	AGV01	go_to	17	completed	2026-06-05 08:58:15.49005+07	2026-06-05 08:58:15.49005+07	2026-06-05 08:58:47.514706+07	lifecycle:picking:confirmed	mq09yw8fh8r3hdyvnfu	A06
1630	1a6d7b72	AGV02	go_to	17	cancelled	2026-06-05 09:48:27.796722+07	\N	2026-06-05 09:50:15.931243+07	cancelled by user	mq0boupdx7iwru9r66	A06
1549	6db72ee0	AGV02	go_to	17	completed	2026-06-05 08:58:33.506064+07	2026-06-05 08:59:05.62701+07	2026-06-05 08:59:48.075934+07	lifecycle:picking:confirmed	mq09za4gndu3jzcp39g	A06
1625	0a0df1df	AGV02	go_charge	\N	cancelled	2026-06-05 09:46:26.223161+07	\N	2026-06-05 09:50:15.931243+07	cancelled by user	mq0boupdx7iwru9r66	A06
1551	ea81125c	AGV02	go_to	17	completed	2026-06-05 08:59:05.725538+07	2026-06-05 08:59:48.076894+07	2026-06-05 09:00:26.162091+07	lifecycle:picking:confirmed	mq09za4gndu3jzcp39g	A06
1649	67682a8c	AGV02	go_to	64	cancelled	2026-06-05 09:49:52.775253+07	\N	2026-06-05 09:50:15.931243+07	cancelled by user	mq0boupdx7iwru9r66	A06
1550	6a440cd4	AGV02	go_charge	\N	completed	2026-06-05 08:58:33.52307+07	2026-06-05 09:00:26.162091+07	2026-06-05 09:00:38.423779+07		mq09za4gndu3jzcp39g	A06
1620	763690f9	AGV01	go_to	17	completed	2026-06-05 09:46:14.526777+07	2026-06-05 09:46:14.526777+07	2026-06-05 09:46:49.051808+07	lifecycle:picking:confirmed	mq0bolpki3b90cknet	A06
1643	36471dbb	AGV02	go_to	64	cancelled	2026-06-05 09:49:29.224128+07	\N	2026-06-05 09:50:15.931243+07	cancelled by user	mq0boupdx7iwru9r66	A06
1624	6188a388	AGV02	go_to	17	completed	2026-06-05 09:46:26.211145+07	2026-06-05 09:47:53.941968+07	2026-06-05 09:48:10.418374+07		mq0boupdx7iwru9r66	A06
1648	9e73d8ed	AGV01	go_to	4	cancelled	2026-06-05 09:49:46.339551+07	\N	2026-06-05 09:50:23.105533+07	cancelled by user	mq0bolpki3b90cknet	A06
1641	1440140f	AGV02	go_to	9	cancelled	2026-06-05 09:49:22.210012+07	\N	2026-06-05 09:50:15.931243+07	cancelled by user	mq0boupdx7iwru9r66	A06
1645	6bdac1fb	AGV02	go_to	10	cancelled	2026-06-05 09:49:36.369667+07	\N	2026-06-05 09:50:15.931243+07	cancelled by user	mq0boupdx7iwru9r66	A06
1647	473bd55e	AGV02	go_to	9	cancelled	2026-06-05 09:49:43.456453+07	\N	2026-06-05 09:50:15.931243+07	cancelled by user	mq0boupdx7iwru9r66	A06
1639	12dd9208	AGV02	go_to	10	cancelled	2026-06-05 09:49:12.84368+07	\N	2026-06-05 09:50:15.931243+07	cancelled by user	mq0boupdx7iwru9r66	A06
1628	aee44e91	AGV01	go_charge	\N	cancelled	2026-06-05 09:48:00.494932+07	2026-06-05 09:48:19.035302+07	2026-06-05 09:50:23.104533+07	force-cancelled by user	mq0bolpki3b90cknet	A06
1650	ec974d14	AGV01	go_to	9	cancelled	2026-06-05 09:49:53.49052+07	\N	2026-06-05 09:50:23.105533+07	cancelled by user	mq0bolpki3b90cknet	A06
1646	c3c1e544	AGV01	go_to	64	cancelled	2026-06-05 09:49:39.18201+07	\N	2026-06-05 09:50:23.105533+07	cancelled by user	mq0bolpki3b90cknet	A06
1644	8896b57f	AGV01	go_to	9	cancelled	2026-06-05 09:49:32.189996+07	\N	2026-06-05 09:50:23.105533+07	cancelled by user	mq0bolpki3b90cknet	A06
1642	05d9b72c	AGV01	go_to	4	cancelled	2026-06-05 09:49:24.992858+07	\N	2026-06-05 09:50:23.105533+07	cancelled by user	mq0bolpki3b90cknet	A06
1640	f2081ba9	AGV01	go_to	64	cancelled	2026-06-05 09:49:17.921873+07	\N	2026-06-05 09:50:23.105533+07	cancelled by user	mq0bolpki3b90cknet	A06
1638	39221550	AGV01	go_to	9	cancelled	2026-06-05 09:49:10.780184+07	\N	2026-06-05 09:50:23.105533+07	cancelled by user	mq0bolpki3b90cknet	A06
1636	66d23f0d	AGV01	go_to	4	cancelled	2026-06-05 09:49:03.825396+07	\N	2026-06-05 09:50:23.105533+07	cancelled by user	mq0bolpki3b90cknet	A06
1634	3a7784ca	AGV01	go_to	64	cancelled	2026-06-05 09:48:54.612918+07	\N	2026-06-05 09:50:23.105533+07	cancelled by user	mq0bolpki3b90cknet	A06
1632	83120659	AGV01	go_to	13	cancelled	2026-06-05 09:48:38.334878+07	\N	2026-06-05 09:50:23.105533+07	cancelled by user	mq0bolpki3b90cknet	A06
1633	cebfeebf	AGV01	go_to	5	cancelled	2026-06-05 09:48:45.396886+07	\N	2026-06-05 09:50:23.105533+07	cancelled by user	mq0bolpki3b90cknet	A06
2784	6be8b238	AGV01	go_to	17	completed	2026-06-15 10:54:14.987293+07	2026-06-15 10:54:52.063172+07	2026-06-15 10:55:25.965066+07	lifecycle:picking:confirmed	mqeoijy2p8n8127dea	A06
2786	a96fb3d6	AGV02	go_to	19	completed	2026-06-15 10:54:27.559031+07	2026-06-15 10:54:57.178844+07	2026-06-15 10:55:31.81775+07	lifecycle:picking:confirmed	mqeoitsrvggghgun36h	A06
2856	1080f61b	AGV02	go_charge	\N	completed	2026-06-15 13:15:14.37807+07	2026-06-15 13:15:14.37806+07	2026-06-15 13:15:37.825811+07		mqetjvepmigoyfqu2vp	Sạc Pin
2790	f31c76bb	AGV01	go_to	16	completed	2026-06-15 10:56:00.023641+07	2026-06-15 10:56:00.023632+07	2026-06-15 10:56:12.454997+07	parked_siding	mqeoijy2p8n8127dea	yield_siding
2787	e1836862	AGV02	go_to	17	completed	2026-06-15 10:54:27.583502+07	2026-06-15 10:55:31.81791+07	2026-06-15 10:57:27.87058+07	lifecycle:picking:confirmed	mqeoitsrvggghgun36h	A06
2858	c85b2d50	AGV01	go_charge	\N	cancelled	2026-06-15 13:15:34.980472+07	2026-06-15 13:15:34.980458+07	2026-06-15 13:16:00.069048+07	force-cancelled by user	mqetkbbkqx0ggg9mi9e	Sạc Pin
2860	f323fec4	AGV01	go_charge	\N	completed	2026-06-15 13:16:09.167178+07	2026-06-15 13:16:24.227352+07	2026-06-15 13:17:17.410308+07	charge_arrived	mqetl1ogglfgicrv2uf	Sạc Pin
2937	1b2de104	AGV02	go_to	16	completed	2026-06-16 09:26:03.310747+07	2026-06-16 09:26:32.171235+07	2026-06-16 09:26:49.915353+07		mqg0rsqmxxb3ku08rpf	A06
2939	3fe4a20d	AGV01	go_charge	\N	completed	2026-06-16 09:26:50.94831+07	2026-06-16 09:27:07.825621+07	2026-06-16 09:28:12.621841+07	charge_arrived	mqg0rjaf0o6iev2mwmpr	A06
2947	dba25d4d	AGV02	go_to	16	completed	2026-06-16 09:29:19.850319+07	2026-06-16 09:30:06.952746+07	2026-06-16 09:30:47.457252+07	lifecycle:picking:confirmed	mqg0x7b92ot2vi46f33	A02
624	73c60f11	AGV01	go_to	8	failed	2026-06-02 10:06:04.767522+07	2026-06-02 10:06:04.767522+07	2026-06-02 10:06:04.770849+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
587	ccfd7710	AGV01	go_to	4	completed	2026-06-02 09:59:31.541993+07	2026-06-02 09:59:49.832632+07	2026-06-02 09:59:58.491106+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 6/10
625	2cb0b65f	AGV01	go_to	8	running	2026-06-02 10:06:06.790779+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
589	ab96ebb7	AGV01	go_to	1	completed	2026-06-02 09:59:58.688114+07	2026-06-02 10:00:07.173375+07	2026-06-02 10:00:27.233694+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 6/10
626	54274ef4	AGV01	go_to	8	running	2026-06-02 10:06:08.788737+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
593	7e21f96f	AGV01	go_to	1	completed	2026-06-02 10:00:54.798723+07	2026-06-02 10:01:03.325349+07	2026-06-02 10:01:23.213363+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 7/10
627	dc6ea1b0	AGV01	go_to	8	running	2026-06-02 10:06:10.801228+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
595	cd837fb6	AGV01	go_to	4	completed	2026-06-02 10:01:23.251876+07	2026-06-02 10:01:41.528568+07	2026-06-02 10:01:50.65697+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 8/10
628	bab121f8	AGV01	go_to	8	running	2026-06-02 10:06:12.806048+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
598	ee118451	AGV01	go_to	4	completed	2026-06-02 10:02:19.111148+07	2026-06-02 10:02:19.111148+07	2026-06-02 10:02:37.313326+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 9/10
599	606ff430	AGV01	go_to	4	completed	2026-06-02 10:02:19.119558+07	2026-06-02 10:02:37.314323+07	2026-06-02 10:02:46.46652+07	sim:auto_confirm	064a9bb2ef	Mô phỏng vòng 9/10
600	c202b678	AGV01	go_to	1	completed	2026-06-02 10:02:46.468027+07	2026-06-02 10:02:46.468027+07	2026-06-02 10:02:54.855584+07		064a9bb2ef	Mô phỏng vòng 9/10
601	608af0a6	AGV01	go_to	1	cancelled	2026-06-02 10:02:46.484224+07	2026-06-02 10:02:54.855584+07	2026-06-02 10:04:09.480018+07	force-cancelled by user	064a9bb2ef	Mô phỏng vòng 9/10
602	2008e976	AGV01	go_to	8	completed	2026-06-02 10:05:03.065339+07	2026-06-02 10:05:03.065339+07	2026-06-02 10:05:22.349456+07	sim:auto_confirm	5bde5a0a5b	Mô phỏng vòng 1/10
603	f03bd18d	AGV01	go_to	8	failed	2026-06-02 10:05:22.349456+07	2026-06-02 10:05:22.349456+07	2026-06-02 10:05:22.350454+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
604	ea813372	AGV01	go_to	8	failed	2026-06-02 10:05:24.387114+07	2026-06-02 10:05:24.387114+07	2026-06-02 10:05:24.398114+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
605	d80f60c4	AGV01	go_to	8	failed	2026-06-02 10:05:26.443739+07	2026-06-02 10:05:26.443739+07	2026-06-02 10:05:26.457362+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
606	f110360d	AGV01	go_to	8	failed	2026-06-02 10:05:28.46903+07	2026-06-02 10:05:28.46903+07	2026-06-02 10:05:28.470027+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
607	86e1db96	AGV01	go_to	8	running	2026-06-02 10:05:30.492763+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
608	4a1b16e2	AGV01	go_to	8	failed	2026-06-02 10:05:32.504013+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
609	afa34753	AGV01	go_to	8	failed	2026-06-02 10:05:34.535641+07	2026-06-02 10:05:34.535641+07	2026-06-02 10:05:34.54248+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
610	a97b224a	AGV01	go_to	8	failed	2026-06-02 10:05:36.576613+07	2026-06-02 10:05:36.576613+07	2026-06-02 10:05:36.581625+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
611	996a999e	AGV01	go_to	8	failed	2026-06-02 10:05:38.596992+07	2026-06-02 10:05:38.596992+07	2026-06-02 10:05:38.596992+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
612	38100f62	AGV01	go_to	8	running	2026-06-02 10:05:40.621345+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
613	f487f93a	AGV01	go_to	8	running	2026-06-02 10:05:42.633022+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
614	17b49424	AGV01	go_to	8	failed	2026-06-02 10:05:44.637274+07	2026-06-02 10:05:44.637274+07	2026-06-02 10:05:44.638403+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
615	253d6c8c	AGV01	go_to	8	failed	2026-06-02 10:05:46.663898+07	2026-06-02 10:05:46.663898+07	2026-06-02 10:05:46.666226+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
616	d1f2dae7	AGV01	go_to	8	running	2026-06-02 10:05:48.673949+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
617	18875bd4	AGV01	go_to	8	running	2026-06-02 10:05:50.679396+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
618	71671f6c	AGV01	go_to	8	running	2026-06-02 10:05:52.698642+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
619	da1a15e3	AGV01	go_to	8	running	2026-06-02 10:05:54.711372+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
620	6677be52	AGV01	go_to	8	running	2026-06-02 10:05:56.715164+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
621	3a2a8d1d	AGV01	go_to	8	running	2026-06-02 10:05:58.718731+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
622	03764517	AGV01	go_to	8	running	2026-06-02 10:06:00.734304+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
623	01f7d9d4	AGV01	go_to	8	running	2026-06-02 10:06:02.752021+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
629	34a28f86	AGV01	go_to	8	failed	2026-06-02 10:06:14.837436+07	2026-06-02 10:06:14.837436+07	2026-06-02 10:06:14.838438+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
630	58f9388c	AGV01	go_to	8	failed	2026-06-02 10:06:16.836071+07	2026-06-02 10:06:16.836071+07	2026-06-02 10:06:16.83708+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
631	7311e2dc	AGV01	go_to	8	running	2026-06-02 10:06:18.832176+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
632	34158312	AGV01	go_to	8	failed	2026-06-02 10:06:20.815052+07	2026-06-02 10:06:20.815052+07	2026-06-02 10:06:20.818577+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
633	50ff4c4a	AGV01	go_to	8	running	2026-06-02 10:06:22.822694+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
634	932a7080	AGV01	go_to	8	running	2026-06-02 10:06:24.852784+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
635	661bc851	AGV01	go_to	8	failed	2026-06-02 10:06:26.842856+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
636	1c9b6e63	AGV01	go_to	8	running	2026-06-02 10:06:28.867427+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
637	de208dbc	AGV01	go_to	8	failed	2026-06-02 10:06:30.877055+07	2026-06-02 10:06:30.877055+07	2026-06-02 10:06:30.877055+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
638	1c80ff0c	AGV01	go_to	8	failed	2026-06-02 10:06:32.889461+07	2026-06-02 10:06:32.889461+07	2026-06-02 10:06:32.891664+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
639	dac48d4a	AGV01	go_to	8	failed	2026-06-02 10:06:34.898434+07	2026-06-02 10:06:34.898434+07	2026-06-02 10:06:34.899434+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
640	dc28397e	AGV01	go_to	8	failed	2026-06-02 10:06:36.891641+07	2026-06-02 10:06:36.891641+07	2026-06-02 10:06:36.891641+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
641	c7bdefce	AGV01	go_to	8	failed	2026-06-02 10:06:38.909136+07	2026-06-02 10:06:38.909136+07	2026-06-02 10:06:38.910151+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
642	645b2446	AGV01	go_to	8	running	2026-06-02 10:06:40.921647+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
643	84cfb3c9	AGV01	go_to	8	running	2026-06-02 10:06:42.937967+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
644	31505262	AGV01	go_to	8	running	2026-06-02 10:06:44.963208+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
645	68f2f393	AGV01	go_to	8	failed	2026-06-02 10:06:46.989363+07	2026-06-02 10:06:46.989363+07	2026-06-02 10:06:46.991572+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
646	06626d2b	AGV01	go_to	8	failed	2026-06-02 10:06:49.008256+07	2026-06-02 10:06:49.008256+07	2026-06-02 10:06:49.009273+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
647	e0c33b92	AGV01	go_to	8	failed	2026-06-02 10:06:51.023262+07	2026-06-02 10:06:51.023262+07	2026-06-02 10:06:51.024255+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
648	a2908f43	AGV01	go_to	8	failed	2026-06-02 10:06:53.017066+07	2026-06-02 10:06:53.017066+07	2026-06-02 10:06:53.018081+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
649	d3a58325	AGV01	go_to	8	running	2026-06-02 10:06:55.036781+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
650	aa90fcdb	AGV01	go_to	8	running	2026-06-02 10:06:57.031803+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
651	10a312e2	AGV01	go_to	8	running	2026-06-02 10:06:59.023323+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
652	bbef04af	AGV01	go_to	8	failed	2026-06-02 10:07:01.020048+07	2026-06-02 10:07:01.020048+07	2026-06-02 10:07:01.021243+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
656	bb9bb27b	AGV01	go_to	8	running	2026-06-02 10:07:09.078632+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
657	6599115f	AGV01	go_to	8	failed	2026-06-02 10:07:11.093669+07	2026-06-02 10:07:11.093669+07	2026-06-02 10:07:11.095629+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
658	cd9e308d	AGV01	go_to	8	running	2026-06-02 10:07:13.105248+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
659	5b07227a	AGV01	go_to	8	running	2026-06-02 10:07:15.129219+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
660	bb146aba	AGV01	go_to	8	failed	2026-06-02 10:07:17.128837+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
661	7ee8aee1	AGV01	go_to	8	running	2026-06-02 10:07:19.144663+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
662	fc97a4f2	AGV01	go_to	8	failed	2026-06-02 10:07:21.159561+07	2026-06-02 10:07:21.159561+07	2026-06-02 10:07:21.160551+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
674	4d116a47	AGV01	go_to	8	running	2026-06-02 10:07:45.284007+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
675	e30dfae3	AGV01	go_to	8	running	2026-06-02 10:07:47.280335+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
676	eaa6482a	AGV01	go_to	8	failed	2026-06-02 10:07:49.298185+07	2026-06-02 10:07:49.298185+07	2026-06-02 10:07:49.300188+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
678	f045539b	AGV01	go_to	8	running	2026-06-02 10:07:53.330606+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
679	78d8cb93	AGV01	go_to	8	running	2026-06-02 10:07:55.34352+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
680	f2e97435	AGV01	go_to	8	failed	2026-06-02 10:07:57.366313+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
681	64003860	AGV01	go_to	8	running	2026-06-02 10:07:59.367071+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
682	4eeea3e1	AGV01	go_to	8	running	2026-06-02 10:08:01.366011+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
683	a8d3e7e8	AGV01	go_to	8	running	2026-06-02 10:08:03.378614+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
684	a5d6d9c1	AGV01	go_to	8	failed	2026-06-02 10:08:05.383023+07	2026-06-02 10:08:05.383023+07	2026-06-02 10:08:05.384023+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
1270	cc549c28	AGV01	go_charge	\N	cancelled	2026-06-03 16:39:11.876168+07	2026-06-03 16:39:11.876168+07	2026-06-03 16:39:20.85225+07	force-cancelled by user	mpxvjypsd67djlrtogm	Sạc Pin
1556	e5d350a1	AGV01	go_charge	\N	cancelled	2026-06-05 09:00:50.946565+07	2026-06-05 09:00:50.946565+07	2026-06-05 09:01:01.01421+07	force-cancelled by user	mq0a2871m1hotytea49	Sạc Pin
1554	71df9bf3	AGV02	go_charge	\N	cancelled	2026-06-05 09:00:26.187055+07	2026-06-05 09:00:38.424779+07	2026-06-05 09:01:43.293318+07	force-cancelled by user	mq09za4gndu3jzcp39g	A06
1362	b81cd601	AGV01	go_to	17	completed	2026-06-04 08:49:48.771749+07	2026-06-04 08:50:41.90223+07	2026-06-04 08:51:05.537338+07	lifecycle:picking:confirmed	mpyu86axx7lzlysmqp	A06
1363	86b1f033	AGV01	go_charge	\N	completed	2026-06-04 08:49:48.78474+07	2026-06-04 08:51:05.537338+07	2026-06-04 08:51:13.823292+07		mpyu86axx7lzlysmqp	A06
1555	8e86ee56	AGV02	go_charge	\N	cancelled	2026-06-05 09:00:38.447186+07	\N	2026-06-05 09:01:43.294361+07	cancelled by user	mq09za4gndu3jzcp39g	A06
1364	9b19c5e9	AGV02	go_to	17	completed	2026-06-04 08:50:04.421842+07	2026-06-04 08:50:04.421842+07	2026-06-04 08:51:21.293722+07	lifecycle:picking:confirmed	mpyu8io0o7n99j15qi	A06
1368	61030031	AGV01	go_charge	\N	completed	2026-06-04 08:51:13.845309+07	2026-06-04 08:51:20.966601+07	2026-06-04 08:51:30.225779+07		mpyu86axx7lzlysmqp	A06
1440	1eab56cf	AGV02	go_charge	\N	cancelled	2026-06-04 10:00:34.997435+07	2026-06-04 10:00:41.471464+07	2026-06-04 10:01:12.198073+07	force-cancelled by user	mpywr6z2dnnf54l83c	Sạc Pin
1496	91291ec3	AGV01	go_charge	\N	cancelled	2026-06-04 14:54:22.849453+07	\N	2026-06-04 15:15:24.324788+07	cancelled by user	mpz790of70twsdxqk6	A06
1498	8f69ea47	AGV01	go_charge	\N	completed	2026-06-04 15:16:22.427336+07	2026-06-04 15:16:46.161543+07	2026-06-04 15:16:54.016242+07		mpz81aw7qwe11hy3jw	A06
1500	6be9c6c4	AGV01	go_to	69	completed	2026-06-04 15:17:59.337856+07	2026-06-04 15:17:59.337856+07	2026-06-04 15:18:46.385456+07	lifecycle:picking:confirmed	mpz83dphgq6g7u87m1o	A02
1548	3b9931bf	AGV02	go_to	17	completed	2026-06-05 08:58:33.483548+07	2026-06-05 08:58:33.483548+07	2026-06-05 08:59:05.618997+07	lifecycle:picking:confirmed	mq09za4gndu3jzcp39g	A06
1546	53c004b6	AGV01	go_to	17	completed	2026-06-05 08:58:15.731338+07	2026-06-05 08:58:47.525226+07	2026-06-05 08:59:09.467163+07	lifecycle:picking:confirmed	mq09yw8fh8r3hdyvnfu	A06
1774	24a09657	AGV01	go_to	17	completed	2026-06-05 11:15:44.786697+07	2026-06-05 11:15:44.786697+07	2026-06-05 11:16:21.335416+07	lifecycle:picking:confirmed	mq0evpfqj0casqucjn9	A06
1547	ecafc00a	AGV01	go_charge	\N	cancelled	2026-06-05 08:58:15.74433+07	2026-06-05 08:59:09.468167+07	2026-06-05 09:00:35.932347+07	force-cancelled by user	mq09yw8fh8r3hdyvnfu	A06
1553	dba6213e	AGV01	go_to	18	cancelled	2026-06-05 08:59:34.078676+07	\N	2026-06-05 09:00:35.933367+07	cancelled by user	mq09yw8fh8r3hdyvnfu	A06
1552	b605ff14	AGV01	go_charge	\N	cancelled	2026-06-05 08:59:09.524168+07	\N	2026-06-05 09:00:35.933367+07	cancelled by user	mq09yw8fh8r3hdyvnfu	A06
1899	640514b7	AGV01	go_charge	\N	completed	2026-06-05 13:42:43.317793+07	2026-06-05 13:43:43.882147+07	2026-06-05 13:43:43.895144+07	bounce_wait	mq0k4ppkidezjwnyep	A06
1623	e458ba0f	AGV02	go_to	17	completed	2026-06-05 09:46:26.166171+07	2026-06-05 09:46:26.166171+07	2026-06-05 09:47:35.345472+07	event:continue	mq0boupdx7iwru9r66	A06
1621	e2c217b1	AGV01	go_to	17	completed	2026-06-05 09:46:14.806669+07	2026-06-05 09:46:49.051808+07	2026-06-05 09:48:00.4595+07	lifecycle:picking:confirmed	mq0bolpki3b90cknet	A06
1778	2cc0af05	AGV02	go_to	17	completed	2026-06-05 11:16:03.139465+07	2026-06-05 11:16:37.38774+07	2026-06-05 11:17:18.938718+07		mq0ew3dvswc5dhetxum	A06
1622	2d1493c1	AGV01	go_charge	\N	completed	2026-06-05 09:46:14.826754+07	2026-06-05 09:48:00.4595+07	2026-06-05 09:48:19.013839+07		mq0bolpki3b90cknet	A06
1627	6f9098ab	AGV02	go_to	17	completed	2026-06-05 09:47:53.957098+07	2026-06-05 09:48:10.422376+07	2026-06-05 09:48:27.433308+07		mq0boupdx7iwru9r66	A06
1657	657d33cb	AGV01	go_charge	\N	cancelled	2026-06-05 09:51:46.566984+07	2026-06-05 09:51:46.566984+07	2026-06-05 09:52:11.042054+07	force-cancelled by user	\N	bounce_retry
1726	bccca537	AGV02	go_charge	\N	completed	2026-06-05 10:30:01.803566+07	2026-06-05 10:30:01.803566+07	2026-06-05 10:30:13.2918+07		mq0d8wxkkt4248utvn9	Sạc Pin
1900	eedbb4f0	AGV02	go_to	17	completed	2026-06-05 13:42:59.244394+07	2026-06-05 13:42:59.244394+07	2026-06-05 13:43:34.56047+07	lifecycle:picking:confirmed	mq0k525lckpydkmtaes	A06
1782	5d53189c	AGV02	go_to	17	completed	2026-06-05 11:17:18.946719+07	2026-06-05 11:17:35.276415+07	2026-06-05 11:17:51.826608+07		mq0ew3dvswc5dhetxum	A06
1779	3cc33d05	AGV02	go_charge	\N	cancelled	2026-06-05 11:16:03.170972+07	\N	2026-06-05 11:25:13.240258+07	cancelled by user	mq0ew3dvswc5dhetxum	A06
1812	31fdf748	AGV01	go_to	7	cancelled	2026-06-05 11:34:17.433804+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1898	52258731	AGV01	go_to	17	completed	2026-06-05 13:42:43.298011+07	2026-06-05 13:43:18.648153+07	2026-06-05 13:43:43.882147+07	lifecycle:picking:confirmed	mq0k4ppkidezjwnyep	A06
1909	f1bd2d03	AGV02	go_to	19	cancelled	2026-06-05 13:44:35.562723+07	\N	2026-06-05 13:48:50.856967+07	cancelled by user	mq0k525lckpydkmtaes	A06
1908	734ec16b	AGV02	go_to	8	cancelled	2026-06-05 13:44:28.601146+07	\N	2026-06-05 13:48:50.856967+07	cancelled by user	mq0k525lckpydkmtaes	A06
1907	e793ab46	AGV02	go_to	5	cancelled	2026-06-05 13:44:19.01631+07	\N	2026-06-05 13:48:50.856967+07	cancelled by user	mq0k525lckpydkmtaes	A06
1906	f8dc9d8c	AGV02	go_to	9	cancelled	2026-06-05 13:44:09.600481+07	\N	2026-06-05 13:48:50.856967+07	cancelled by user	mq0k525lckpydkmtaes	A06
1957	d2c5f7bc	AGV02	go_to	69	completed	2026-06-05 15:54:23.983084+07	2026-06-05 15:54:23.983084+07	2026-06-05 15:54:52.601378+07	lifecycle:picking:confirmed	mq0ou21v1akuscsxc7u	A06
1940	5b4a07ea	AGV02	go_charge	\N	completed	2026-06-05 14:36:57.90194+07	2026-06-05 14:37:13.20277+07	2026-06-05 14:37:42.465422+07	charge_arrived	mq0m1vq5hmrmfui3rn	A06
1965	97525da0	AGV02	go_to	69	completed	2026-06-05 15:58:30.931087+07	2026-06-05 15:59:01.122675+07	2026-06-05 15:59:16.436163+07		mq0ozclas3up3vfyj4q	A02
653	eeedf949	AGV01	go_to	8	failed	2026-06-02 10:07:03.018377+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
654	23693882	AGV01	go_to	8	running	2026-06-02 10:07:05.018466+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
655	d0fa6b7c	AGV01	go_to	8	failed	2026-06-02 10:07:07.054181+07	2026-06-02 10:07:07.054181+07	2026-06-02 10:07:07.055198+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
663	fd66126b	AGV01	go_to	8	running	2026-06-02 10:07:23.169656+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
664	cce31ce9	AGV01	go_to	8	running	2026-06-02 10:07:25.197012+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
665	07518684	AGV01	go_to	8	running	2026-06-02 10:07:27.208453+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
666	9ebbd38f	AGV01	go_to	8	running	2026-06-02 10:07:29.208388+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
667	6e7232bc	AGV01	go_to	8	running	2026-06-02 10:07:31.218101+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
668	7cb0bb45	AGV01	go_to	8	running	2026-06-02 10:07:33.235223+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
669	6c9545af	AGV01	go_to	8	failed	2026-06-02 10:07:35.261904+07	2026-06-02 10:07:35.261904+07	2026-06-02 10:07:35.26796+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
670	fe3ddc15	AGV01	go_to	8	running	2026-06-02 10:07:37.285615+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
671	0d87cf1a	AGV01	go_to	8	running	2026-06-02 10:07:39.290141+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
672	8188347d	AGV01	go_to	8	failed	2026-06-02 10:07:41.289331+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
673	06fee049	AGV01	go_to	8	failed	2026-06-02 10:07:43.262627+07	2026-06-02 10:07:43.262627+07	2026-06-02 10:07:43.262627+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
677	23ad3cfc	AGV01	go_to	8	failed	2026-06-02 10:07:51.318668+07	2026-06-02 10:07:51.318668+07	2026-06-02 10:07:51.319705+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
685	b5765910	AGV01	go_to	8	failed	2026-06-02 10:08:07.382135+07	2026-06-02 10:08:07.382135+07	2026-06-02 10:08:07.383139+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
686	c2a56694	AGV01	go_to	8	failed	2026-06-02 10:08:09.384744+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
687	837efa44	AGV01	go_to	8	running	2026-06-02 10:08:11.386529+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
688	9ec9075a	AGV01	go_to	8	failed	2026-06-02 10:08:13.403372+07	2026-06-02 10:08:13.403372+07	2026-06-02 10:08:13.404578+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
689	173fbc02	AGV01	go_to	8	failed	2026-06-02 10:08:15.418817+07	2026-06-02 10:08:15.418817+07	2026-06-02 10:08:15.420813+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
690	0a4b82bb	AGV01	go_to	8	failed	2026-06-02 10:08:17.433109+07	2026-06-02 10:08:17.433109+07	2026-06-02 10:08:17.434319+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
691	150d7009	AGV01	go_to	8	failed	2026-06-02 10:08:19.44813+07	2026-06-02 10:08:19.44813+07	2026-06-02 10:08:19.449118+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
692	060517d7	AGV01	go_to	8	failed	2026-06-02 10:08:21.444931+07	2026-06-02 10:08:21.444931+07	2026-06-02 10:08:21.445922+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
693	04bb2c8b	AGV01	go_to	8	running	2026-06-02 10:08:23.451984+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
694	2b2f3c56	AGV01	go_to	8	running	2026-06-02 10:08:25.473815+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
695	8f38b72d	AGV01	go_to	8	running	2026-06-02 10:08:27.466627+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
696	ec0d6a57	AGV01	go_to	8	running	2026-06-02 10:08:29.483145+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
697	555ab199	AGV01	go_to	8	running	2026-06-02 10:08:31.497246+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
698	9b76d1c6	AGV01	go_to	8	failed	2026-06-02 10:08:33.545425+07	2026-06-02 10:08:33.545425+07	2026-06-02 10:08:33.559424+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
699	1320109e	AGV01	go_to	8	failed	2026-06-02 10:08:35.578676+07	2026-06-02 10:08:35.578676+07	2026-06-02 10:08:35.578676+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
700	e0569191	AGV01	go_to	8	running	2026-06-02 10:08:37.602445+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
701	0381a62c	AGV01	go_to	8	running	2026-06-02 10:08:39.614983+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
702	49d9e164	AGV01	go_to	8	running	2026-06-02 10:08:41.63633+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
703	87532afa	AGV01	go_to	8	failed	2026-06-02 10:08:43.64842+07	2026-06-02 10:08:43.64842+07	2026-06-02 10:08:43.649931+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
704	05fc7820	AGV01	go_to	8	running	2026-06-02 10:08:45.649795+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
705	6a43b710	AGV01	go_to	8	failed	2026-06-02 10:08:47.647321+07	2026-06-02 10:08:47.647321+07	2026-06-02 10:08:47.648328+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
706	2203da20	AGV01	go_to	8	running	2026-06-02 10:08:49.647648+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
707	d0890d5e	AGV01	go_to	8	running	2026-06-02 10:08:51.638634+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
708	3fa4850e	AGV01	go_to	8	running	2026-06-02 10:08:53.663766+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
709	74a887b4	AGV01	go_to	8	failed	2026-06-02 10:08:55.668846+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
710	ef1df8d9	AGV01	go_to	8	failed	2026-06-02 10:08:57.684052+07	2026-06-02 10:08:57.684052+07	2026-06-02 10:08:57.685042+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
711	e12f352d	AGV01	go_to	8	running	2026-06-02 10:08:59.726072+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
712	3afd9d05	AGV01	go_to	8	failed	2026-06-02 10:09:01.731742+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
713	2cae7d6e	AGV01	go_to	8	running	2026-06-02 10:09:03.738175+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
714	2df41358	AGV01	go_to	8	running	2026-06-02 10:09:05.756518+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
715	93294bff	AGV01	go_to	8	running	2026-06-02 10:09:07.758518+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
716	5d3678c2	AGV01	go_to	8	running	2026-06-02 10:09:09.78506+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
717	408e245e	AGV01	go_to	8	running	2026-06-02 10:09:11.769793+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
718	0a766a4f	AGV01	go_to	8	running	2026-06-02 10:09:13.776199+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
719	9c1ecb10	AGV01	go_to	8	running	2026-06-02 10:09:15.774143+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
720	04a92311	AGV01	go_to	8	failed	2026-06-02 10:09:17.793558+07	2026-06-02 10:09:17.793558+07	2026-06-02 10:09:17.793558+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
721	f4da2752	AGV01	go_to	8	failed	2026-06-02 10:09:19.828128+07	2026-06-02 10:09:19.828128+07	2026-06-02 10:09:19.838122+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
722	d14f3d4d	AGV01	go_to	8	failed	2026-06-02 10:09:21.880699+07	2026-06-02 10:09:21.880699+07	2026-06-02 10:09:21.886701+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
723	099678bc	AGV01	go_to	8	running	2026-06-02 10:09:23.915774+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
724	13798c9c	AGV01	go_to	8	running	2026-06-02 10:09:25.905213+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
725	1086b4c9	AGV01	go_to	8	running	2026-06-02 10:09:27.91146+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
726	cb68e038	AGV01	go_to	8	failed	2026-06-02 10:09:29.915472+07	2026-06-02 10:09:29.915472+07	2026-06-02 10:09:29.919477+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
727	e031e565	AGV01	go_to	8	failed	2026-06-02 10:09:31.97867+07	2026-06-02 10:09:31.97867+07	2026-06-02 10:09:31.98866+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
728	859c3df0	AGV01	go_to	8	running	2026-06-02 10:09:34.014444+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
729	469d63c2	AGV01	go_to	8	running	2026-06-02 10:09:36.03817+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
730	4b8537de	AGV01	go_to	8	running	2026-06-02 10:09:38.071192+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
731	edc5cf35	AGV01	go_to	8	running	2026-06-02 10:09:40.082377+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
732	a090f33b	AGV01	go_to	8	failed	2026-06-02 10:09:42.0627+07	2026-06-02 10:09:42.0627+07	2026-06-02 10:09:42.063704+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
735	c5179a75	AGV01	go_to	8	running	2026-06-02 10:09:48.1495+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
736	da7e9142	AGV01	go_to	8	failed	2026-06-02 10:09:50.168713+07	2026-06-02 10:09:50.168713+07	2026-06-02 10:09:50.169717+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
738	daec7b72	AGV01	go_to	8	running	2026-06-02 10:09:54.201901+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
739	e7e72d47	AGV01	go_to	8	running	2026-06-02 10:09:56.219585+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
740	c1da9386	AGV01	go_to	8	failed	2026-06-02 10:09:58.222545+07	2026-06-02 10:09:58.222545+07	2026-06-02 10:09:58.222545+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
751	3bca8354	AGV01	go_to	8	failed	2026-06-02 10:10:20.359558+07	2026-06-02 10:10:20.359558+07	2026-06-02 10:10:20.361559+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
752	c408ecef	AGV01	go_to	8	failed	2026-06-02 10:10:22.378461+07	2026-06-02 10:10:22.378461+07	2026-06-02 10:10:22.380459+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
756	77623196	AGV01	go_to	8	running	2026-06-02 10:10:30.36424+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
757	62e0213f	AGV01	go_to	8	running	2026-06-02 10:10:32.377168+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
758	46d05567	AGV01	go_to	8	failed	2026-06-02 10:10:34.38308+07	2026-06-02 10:10:34.38308+07	2026-06-02 10:10:34.385077+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
760	fdc74eed	AGV01	go_to	8	failed	2026-06-02 10:10:38.395829+07	2026-06-02 10:10:38.395829+07	2026-06-02 10:10:38.396878+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
762	86d5b322	AGV01	go_to	8	cancelled	2026-06-02 10:10:42.405498+07	2026-06-02 10:10:42.405498+07	2026-06-02 10:11:04.875116+07	force-cancelled by user	5bde5a0a5b	Mô phỏng vòng 2/10
764	3b4b16cc	AGV01	go_to	8	cancelled	2026-06-02 10:11:28.135582+07	2026-06-02 10:11:28.135582+07	2026-06-02 10:14:37.554877+07	force-cancelled by user	e60613d221	Mô phỏng vòng 1/10
767	1390ff33	AGV01	go_to	5	completed	2026-06-02 10:14:55.428097+07	2026-06-02 10:15:21.603825+07	2026-06-02 10:15:21.733347+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 1/10
1271	f656c649	AGV01	go_to	17	completed	2026-06-03 16:40:37.833286+07	2026-06-03 16:40:37.833286+07	2026-06-03 16:41:14.388517+07	lifecycle:picking:confirmed	mpxvlt1eo8wkq5ur75	A06
1904	51e168b5	AGV01	go_charge	\N	completed	2026-06-05 13:43:44.38891+07	2026-06-05 13:43:44.38891+07	2026-06-05 13:43:59.936331+07		\N	bounce_retry
1273	fbf80b3b	AGV01	go_charge	\N	completed	2026-06-03 16:40:38.060769+07	2026-06-03 16:41:32.902235+07	2026-06-03 16:41:38.145624+07		mpxvlt1eo8wkq5ur75	A06
1274	c20604b4	AGV02	go_to	17	cancelled	2026-06-03 16:40:52.431351+07	2026-06-03 16:40:52.431351+07	2026-06-03 16:47:50.354659+07	force-cancelled by user	mpxvm4anj269exs3y3	A06
1275	65fdd5ce	AGV02	go_to	17	cancelled	2026-06-03 16:40:52.453358+07	\N	2026-06-03 16:47:50.355659+07	cancelled by user	mpxvm4anj269exs3y3	A06
1276	7274bd95	AGV02	go_charge	\N	cancelled	2026-06-03 16:40:52.464368+07	\N	2026-06-03 16:47:50.355659+07	cancelled by user	mpxvm4anj269exs3y3	A06
1503	35352c1e	AGV01	go_to	18	completed	2026-06-04 15:18:46.44098+07	2026-06-04 15:18:52.23144+07	2026-06-04 15:19:36.17604+07	lifecycle:picking:confirmed	mpz83dphgq6g7u87m1o	A02
1375	8c657704	AGV02	go_to	15	cancelled	2026-06-04 08:52:08.633978+07	2026-06-04 08:52:16.789287+07	2026-06-04 08:54:37.359864+07	force-cancelled by user	mpyu8io0o7n99j15qi	A06
1374	d0cd674a	AGV02	go_to	9	cancelled	2026-06-04 08:52:01.55193+07	\N	2026-06-04 08:54:37.359864+07	cancelled by user	mpyu8io0o7n99j15qi	A06
1373	0e30cf95	AGV02	go_to	10	cancelled	2026-06-04 08:51:51.245475+07	\N	2026-06-04 08:54:37.359864+07	cancelled by user	mpyu8io0o7n99j15qi	A06
1372	aa04a7d2	AGV02	go_to	17	cancelled	2026-06-04 08:51:44.247953+07	\N	2026-06-04 08:54:37.359864+07	cancelled by user	mpyu8io0o7n99j15qi	A06
1369	6d7776c4	AGV01	go_charge	\N	cancelled	2026-06-04 08:51:21.065936+07	2026-06-04 08:51:30.226779+07	2026-06-04 08:54:43.365576+07	force-cancelled by user	mpyu86axx7lzlysmqp	A06
1371	e28176d5	AGV01	go_to	5	cancelled	2026-06-04 08:51:41.136233+07	\N	2026-06-04 08:54:43.366576+07	cancelled by user	mpyu86axx7lzlysmqp	A06
1370	56a6929b	AGV01	go_charge	\N	cancelled	2026-06-04 08:51:30.245615+07	\N	2026-06-04 08:54:43.366576+07	cancelled by user	mpyu86axx7lzlysmqp	A06
1442	9bb5156b	AGV01	go_to	17	completed	2026-06-04 10:05:42.706604+07	2026-06-04 10:05:42.706604+07	2026-06-04 10:06:15.47127+07	lifecycle:picking:confirmed	mpywxsed5i3kvdb5lna	A06
1558	9a5687d2	AGV01	go_to	14	cancelled	2026-06-05 09:01:00.378583+07	\N	2026-06-05 09:01:01.016186+07	cancelled by user	mq0a2871m1hotytea49	Sạc Pin
1451	ef82b8b5	AGV01	go_to	13	completed	2026-06-04 10:07:05.424269+07	2026-06-04 10:07:13.405178+07	2026-06-04 10:07:29.824439+07	lifecycle:picking:confirmed	\N	bounce_retry
1446	8d68e81b	AGV02	go_to	17	completed	2026-06-04 10:06:00.500493+07	2026-06-04 10:06:42.573456+07	2026-06-04 10:09:13.466372+07	lifecycle:picking:confirmed	mpywy64m1o4fy88ppn	A06
1557	504c9a74	AGV02	go_to	8	cancelled	2026-06-05 09:00:54.722332+07	\N	2026-06-05 09:01:43.294361+07	cancelled by user	mq09za4gndu3jzcp39g	A06
1447	aab88b5e	AGV02	go_charge	\N	completed	2026-06-04 10:06:00.522255+07	2026-06-04 10:09:13.467389+07	2026-06-04 10:09:56.359057+07	charge_arrived	mpywy64m1o4fy88ppn	A06
1497	704474f6	AGV01	go_to	96	completed	2026-06-04 15:16:22.386949+07	2026-06-04 15:16:22.386949+07	2026-06-04 15:16:46.161543+07	lifecycle:picking:confirmed	mpz81aw7qwe11hy3jw	A06
1559	ace6b7b0	AGV02	go_charge	\N	completed	2026-06-05 09:01:50.828216+07	2026-06-05 09:01:50.828216+07	2026-06-05 09:02:22.489826+07	charge_arrived	mq0a3iefb4vt79m2n3k	Sạc Pin
1777	7ca4cdbe	AGV02	go_to	17	completed	2026-06-05 11:16:02.856678+07	2026-06-05 11:16:02.856678+07	2026-06-05 11:16:37.38774+07	lifecycle:picking:confirmed	mq0ew3dvswc5dhetxum	A06
1626	4cb8ba3d	AGV02	go_to	19	completed	2026-06-05 09:46:55.514016+07	2026-06-05 09:47:35.346791+07	2026-06-05 09:47:53.941968+07	lifecycle:picking:confirmed	mq0boupdx7iwru9r66	A06
1629	f8907610	AGV02	go_to	17	cancelled	2026-06-05 09:48:10.571168+07	2026-06-05 09:48:27.435209+07	2026-06-05 09:50:15.930277+07	force-cancelled by user	mq0boupdx7iwru9r66	A06
1775	5a70ed6d	AGV01	go_to	17	completed	2026-06-05 11:15:44.839209+07	2026-06-05 11:16:21.335416+07	2026-06-05 11:16:43.491223+07	lifecycle:picking:confirmed	mq0evpfqj0casqucjn9	A06
1727	6e8739ac	AGV02	go_charge	\N	completed	2026-06-05 10:30:01.842551+07	2026-06-05 10:30:13.293698+07	2026-06-05 10:30:44.539084+07	charge_arrived	mq0d8wxkkt4248utvn9	Sạc Pin
1776	76c6716b	AGV01	go_charge	\N	cancelled	2026-06-05 11:15:44.853213+07	2026-06-05 11:16:43.491223+07	2026-06-05 11:25:03.686561+07	force-cancelled by user	mq0evpfqj0casqucjn9	A06
1780	a4b90ddb	AGV02	go_to	17	completed	2026-06-05 11:16:37.398249+07	2026-06-05 11:17:18.939719+07	2026-06-05 11:17:35.276415+07		mq0ew3dvswc5dhetxum	A06
1781	f464f1f7	AGV01	go_charge	\N	cancelled	2026-06-05 11:16:43.51776+07	\N	2026-06-05 11:25:03.688555+07	cancelled by user	mq0evpfqj0casqucjn9	A06
1783	f3af43b9	AGV02	go_to	17	cancelled	2026-06-05 11:17:35.290408+07	2026-06-05 11:17:51.826608+07	2026-06-05 11:25:13.239267+07	force-cancelled by user	mq0ew3dvswc5dhetxum	A06
1810	de3565ce	AGV01	go_to	8	cancelled	2026-06-05 11:34:07.8926+07	\N	2026-06-05 11:37:29.888038+07	cancelled by user	\N	bounce_retry
1941	05a168ed	AGV02	go_to	69	completed	2026-06-05 14:56:08.466872+07	2026-06-05 14:56:08.466872+07	2026-06-05 14:56:40.549018+07	lifecycle:picking:confirmed	mq0mr4w13sr8s47b7iq	A06
2782	7d475bf6	AGV01	go_to	19	completed	2026-06-15 10:54:14.826745+07	2026-06-15 10:54:14.826738+07	2026-06-15 10:54:52.06293+07	lifecycle:picking:confirmed	mqeoijy2p8n8127dea	A06
1958	7ff7316a	AGV02	go_to	69	completed	2026-06-05 15:54:24.03082+07	2026-06-05 15:54:52.601378+07	2026-06-05 15:55:08.204492+07		mq0ou21v1akuscsxc7u	A06
1959	254a3238	AGV02	go_charge	\N	completed	2026-06-05 15:54:24.049396+07	2026-06-05 15:55:43.462006+07	2026-06-05 15:56:30.711517+07	off_route	mq0ou21v1akuscsxc7u	A06
1968	51a38130	AGV02	go_to	69	cancelled	2026-06-05 15:59:01.155194+07	2026-06-05 15:59:16.438177+07	2026-06-05 16:00:56.287899+07	force-cancelled by user	mq0ozclas3up3vfyj4q	A02
1986	e0fec625	AGV02	go_to	17	completed	2026-06-05 16:09:42.366445+07	2026-06-05 16:11:43.527586+07	2026-06-05 16:12:04.285699+07	lifecycle:picking:confirmed	mq0pacqsb8k14wijidp	A05
1987	9692a93f	AGV02	go_to	16	completed	2026-06-05 16:12:04.479129+07	2026-06-05 16:12:19.142856+07	2026-06-05 16:12:49.43281+07	lifecycle:picking:confirmed	mq0pacqsb8k14wijidp	A05
733	a39d4a61	AGV01	go_to	8	running	2026-06-02 10:09:44.092844+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
734	6c80652b	AGV01	go_to	8	failed	2026-06-02 10:09:46.135521+07	2026-06-02 10:09:46.135521+07	2026-06-02 10:09:46.135521+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
737	37b890da	AGV01	go_to	8	failed	2026-06-02 10:09:52.189448+07	2026-06-02 10:09:52.189448+07	2026-06-02 10:09:52.19045+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
741	2668b76b	AGV01	go_to	8	running	2026-06-02 10:10:00.232439+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
742	9822137c	AGV01	go_to	8	running	2026-06-02 10:10:02.260486+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
743	6d961d46	AGV01	go_to	8	running	2026-06-02 10:10:04.281218+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
744	07c22454	AGV01	go_to	8	failed	2026-06-02 10:10:06.291325+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
745	6ea42ca2	AGV01	go_to	8	running	2026-06-02 10:10:08.323186+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
746	b2b508aa	AGV01	go_to	8	failed	2026-06-02 10:10:10.320007+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
747	65698745	AGV01	go_to	8	failed	2026-06-02 10:10:12.331509+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
748	aa7707b1	AGV01	go_to	8	running	2026-06-02 10:10:14.338366+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
749	11ae96fa	AGV01	go_to	8	failed	2026-06-02 10:10:16.329069+07	2026-06-02 10:10:16.329069+07	2026-06-02 10:10:16.331067+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
750	5e7ab0ab	AGV01	go_to	8	failed	2026-06-02 10:10:18.348953+07	2026-06-02 10:10:18.348953+07	2026-06-02 10:10:18.349968+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
753	2d3a23fa	AGV01	go_to	8	running	2026-06-02 10:10:24.355819+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
754	497c8adf	AGV01	go_to	8	running	2026-06-02 10:10:26.37518+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
755	76910009	AGV01	go_to	8	running	2026-06-02 10:10:28.38064+07	\N	\N	\N	5bde5a0a5b	Mô phỏng vòng 2/10
759	84c76f18	AGV01	go_to	8	failed	2026-06-02 10:10:36.370499+07	2026-06-02 10:10:36.370499+07	2026-06-02 10:10:36.371497+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
761	ea62cacb	AGV01	go_to	8	failed	2026-06-02 10:10:40.393115+07	2026-06-02 10:10:40.393115+07	2026-06-02 10:10:40.394117+07	AGV01: đã ở tại 8	5bde5a0a5b	Mô phỏng vòng 2/10
763	17da205d	AGV01	go_to	8	cancelled	2026-06-02 10:10:42.455151+07	\N	2026-06-02 10:11:04.875116+07	cancelled by user	5bde5a0a5b	Mô phỏng vòng 2/10
765	cdcb7487	AGV01	go_to	8	cancelled	2026-06-02 10:11:28.152708+07	\N	2026-06-02 10:14:37.554877+07	cancelled by user	e60613d221	Mô phỏng vòng 1/10
766	a305ff74	AGV01	go_to	5	completed	2026-06-02 10:14:55.396053+07	2026-06-02 10:14:55.396053+07	2026-06-02 10:15:21.597869+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 1/10
778	a2161d35	AGV01	go_to	2	completed	2026-06-02 10:18:41.486961+07	2026-06-02 10:18:41.486961+07	2026-06-02 10:18:46.595402+07		c910d78a30	Mô phỏng vòng 3/10
768	37791ce5	AGV01	go_to	2	completed	2026-06-02 10:15:35.484703+07	2026-06-02 10:15:35.484703+07	2026-06-02 10:15:40.614052+07		c910d78a30	Mô phỏng vòng 1/10
769	07ab2616	AGV01	go_to	2	completed	2026-06-02 10:15:35.498754+07	2026-06-02 10:15:40.616138+07	2026-06-02 10:15:51.593563+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 1/10
786	0431324f	AGV01	go_to	2	completed	2026-06-02 10:19:50.902484+07	2026-06-02 10:19:57.359003+07	2026-06-02 10:20:08.5317+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 4/10
770	2591acaf	AGV01	go_to	2	completed	2026-06-02 10:15:40.632205+07	2026-06-02 10:15:51.593563+07	2026-06-02 10:15:51.692876+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 1/10
771	bd4f9bd7	AGV01	go_to	5	completed	2026-06-02 10:16:11.489159+07	2026-06-02 10:16:11.489159+07	2026-06-02 10:16:26.651634+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 2/10
772	2911968f	AGV01	go_to	5	completed	2026-06-02 10:16:11.514213+07	2026-06-02 10:16:26.651634+07	2026-06-02 10:16:26.793444+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 2/10
779	6d373e7f	AGV01	go_to	2	completed	2026-06-02 10:18:41.593233+07	2026-06-02 10:18:46.596419+07	2026-06-02 10:18:59.407287+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 3/10
773	d0ed1d46	AGV01	go_to	2	completed	2026-06-02 10:16:40.513171+07	2026-06-02 10:16:40.513171+07	2026-06-02 10:16:46.122391+07		c910d78a30	Mô phỏng vòng 2/10
774	3e78772c	AGV01	go_to	2	completed	2026-06-02 10:16:40.529123+07	2026-06-02 10:16:46.122391+07	2026-06-02 10:16:56.990944+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 2/10
794	9a6f98bb	AGV01	go_to	8	cancelled	2026-06-02 10:21:28.304655+07	\N	2026-06-02 10:22:15.310047+07	cancelled by user	e60613d221	Mô phỏng vòng 1/10
775	54baac89	AGV01	go_to	2	completed	2026-06-02 10:16:46.141389+07	2026-06-02 10:16:56.990944+07	2026-06-02 10:16:57.084417+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 2/10
776	c3a5942b	AGV01	go_to	5	completed	2026-06-02 10:18:10.550814+07	2026-06-02 10:18:10.550814+07	2026-06-02 10:18:27.832812+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 3/10
780	2a7537ed	AGV01	go_to	2	completed	2026-06-02 10:18:46.629375+07	2026-06-02 10:18:59.407287+07	2026-06-02 10:18:59.640426+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 3/10
777	2ba32430	AGV01	go_to	5	completed	2026-06-02 10:18:10.562939+07	2026-06-02 10:18:27.832812+07	2026-06-02 10:18:27.833828+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 3/10
781	365365d2	AGV01	go_to	5	completed	2026-06-02 10:19:19.239583+07	2026-06-02 10:19:19.239583+07	2026-06-02 10:19:19.345632+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 4/10
787	3dec99be	AGV01	go_to	2	completed	2026-06-02 10:19:57.386394+07	2026-06-02 10:20:08.5317+07	2026-06-02 10:20:08.532585+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 4/10
782	a09da0ae	AGV01	go_to	5	completed	2026-06-02 10:19:19.266905+07	2026-06-02 10:19:19.345632+07	2026-06-02 10:19:37.232912+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 4/10
783	2488857e	AGV01	go_to	5	completed	2026-06-02 10:19:19.35845+07	2026-06-02 10:19:37.241913+07	2026-06-02 10:19:37.568158+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 4/10
784	a58b2c50	AGV01	go_to	2	completed	2026-06-02 10:19:50.268815+07	2026-06-02 10:19:50.268815+07	2026-06-02 10:19:50.881391+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 4/10
785	7b937c20	AGV01	go_to	2	completed	2026-06-02 10:19:50.278829+07	2026-06-02 10:19:50.881391+07	2026-06-02 10:19:57.353372+07		c910d78a30	Mô phỏng vòng 4/10
791	45290397	AGV01	go_to	2	completed	2026-06-02 10:20:57.424441+07	2026-06-02 10:21:02.36632+07	2026-06-02 10:21:13.55815+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 5/10
789	574c9a5d	AGV01	go_to	5	completed	2026-06-02 10:20:28.373986+07	2026-06-02 10:20:43.637586+07	2026-06-02 10:20:43.638578+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 5/10
788	9c30d5ee	AGV01	go_to	5	completed	2026-06-02 10:20:28.344009+07	2026-06-02 10:20:28.344009+07	2026-06-02 10:20:43.637586+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 5/10
790	899dc977	AGV01	go_to	2	completed	2026-06-02 10:20:57.402495+07	2026-06-02 10:20:57.402495+07	2026-06-02 10:21:02.36632+07		c910d78a30	Mô phỏng vòng 5/10
793	65c8be1f	AGV01	go_to	8	cancelled	2026-06-02 10:21:28.280547+07	2026-06-02 10:21:28.280547+07	2026-06-02 10:22:19.984108+07	force-cancelled by user	e60613d221	Mô phỏng vòng 1/10
792	a86985f6	AGV01	go_to	2	completed	2026-06-02 10:21:02.386378+07	2026-06-02 10:21:13.55815+07	2026-06-02 10:21:13.747859+07	sim:auto_confirm	c910d78a30	Mô phỏng vòng 5/10
795	0d514b4c	AGV01	go_to	5	cancelled	2026-06-02 10:21:34.166396+07	\N	2026-06-02 10:23:02.39154+07	cancelled by user	c910d78a30	Mô phỏng vòng 6/10
796	2120153b	AGV01	go_to	4	completed	2026-06-02 10:27:51.05319+07	2026-06-02 10:27:51.05319+07	2026-06-02 10:28:00.085915+07	sim:auto_confirm	508aa13650	Mô phỏng vòng 1/10
797	9c1a4bde	AGV01	go_to	18	completed	2026-06-02 10:28:00.132527+07	2026-06-02 10:28:00.132527+07	2026-06-02 10:28:05.910882+07	sim:auto_confirm	508aa13650	Mô phỏng vòng 1/10
798	5f8392c4	AGV01	go_to	5	completed	2026-06-02 10:28:05.913354+07	2026-06-02 10:28:05.913354+07	2026-06-02 10:28:11.496222+07	sim:auto_confirm	508aa13650	Mô phỏng vòng 1/10
799	1ba1ec26	AGV01	go_to	17	completed	2026-06-02 10:28:11.498228+07	2026-06-02 10:28:11.498228+07	2026-06-02 10:28:17.12959+07	sim:auto_confirm	508aa13650	Mô phỏng vòng 1/10
800	ffa3a05e	AGV01	go_to	6	completed	2026-06-02 10:28:17.130571+07	2026-06-02 10:28:17.130571+07	2026-06-02 10:28:23.680373+07	sim:auto_confirm	508aa13650	Mô phỏng vòng 1/10
801	006d0076	AGV01	go_to	7	completed	2026-06-02 10:28:23.694378+07	2026-06-02 10:28:23.694378+07	2026-06-02 10:28:36.304074+07	sim:auto_confirm	508aa13650	Mô phỏng vòng 1/10
2785	9b2dbd0a	AGV02	go_to	19	completed	2026-06-15 10:54:27.55155+07	2026-06-15 10:54:27.551544+07	2026-06-15 10:54:57.178542+07		mqeoitsrvggghgun36h	A06
802	c30567e3	AGV01	go_to	16	completed	2026-06-02 10:28:36.304074+07	2026-06-02 10:28:36.304074+07	2026-06-02 10:29:18.352877+07	sim:auto_confirm	508aa13650	Mô phỏng vòng 1/10
803	a5e43337	AGV01	go_to	8	completed	2026-06-02 10:29:18.35389+07	2026-06-02 10:29:18.35389+07	2026-06-02 10:29:23.918243+07	sim:auto_confirm	508aa13650	Mô phỏng vòng 1/10
804	6ce0ec45	AGV01	go_to	15	completed	2026-06-02 10:29:23.92035+07	2026-06-02 10:29:23.92035+07	2026-06-02 10:29:31.548385+07	sim:auto_confirm	508aa13650	Mô phỏng vòng 1/10
1272	892aea86	AGV01	go_to	17	completed	2026-06-03 16:40:38.047487+07	2026-06-03 16:41:14.388517+07	2026-06-03 16:41:32.901234+07	lifecycle:picking:confirmed	mpxvlt1eo8wkq5ur75	A06
1283	7be4849a	AGV01	go_to	19	cancelled	2026-06-03 16:42:25.921203+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1282	8cad3306	AGV01	go_to	9	cancelled	2026-06-03 16:42:18.948985+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1281	4cf892cb	AGV01	go_to	19	cancelled	2026-06-03 16:42:11.889302+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1280	ace158f7	AGV01	go_to	9	cancelled	2026-06-03 16:42:04.892425+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1279	d966e45b	AGV01	go_to	13	cancelled	2026-06-03 16:41:57.902829+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1376	4f37d632	AGV02	go_to	15	cancelled	2026-06-04 08:52:29.315465+07	\N	2026-06-04 08:54:37.359864+07	cancelled by user	mpyu8io0o7n99j15qi	A06
1565	970d8e0f	AGV01	go_charge	\N	completed	2026-06-05 09:02:55.006902+07	2026-06-05 09:06:01.189046+07	2026-06-05 09:06:38.192396+07	charge_arrived	mq0a4vpxw5yohn54xeo	A06
1570	3fb5aae0	AGV02	go_to	69	completed	2026-06-05 09:06:13.955459+07	2026-06-05 09:06:13.955459+07	2026-06-05 09:06:44.467744+07	lifecycle:picking:confirmed	mq0a95fhi9ykglumtbf	A06
1443	c6c412bf	AGV01	go_to	17	completed	2026-06-04 10:05:42.861345+07	2026-06-04 10:06:15.472497+07	2026-06-04 10:06:33.421736+07	lifecycle:picking:confirmed	mpywxsed5i3kvdb5lna	A06
1445	25574cc4	AGV02	go_to	17	completed	2026-06-04 10:06:00.460626+07	2026-06-04 10:06:00.460626+07	2026-06-04 10:06:42.572454+07	lifecycle:picking:confirmed	mpywy64m1o4fy88ppn	A06
1444	89451383	AGV01	go_charge	\N	completed	2026-06-04 10:05:42.883276+07	2026-06-04 10:06:33.421736+07	2026-06-04 10:06:42.68814+07		mpywxsed5i3kvdb5lna	A06
1448	5a09b050	AGV01	go_charge	\N	completed	2026-06-04 10:06:33.450538+07	2026-06-04 10:06:42.690572+07	2026-06-04 10:06:42.739228+07	bounce_wait	mpywxsed5i3kvdb5lna	A06
1449	485bc029	AGV01	go_charge	\N	completed	2026-06-04 10:06:52.178224+07	2026-06-04 10:06:52.178224+07	2026-06-04 10:07:05.400253+07		\N	bounce_retry
1858	208231a0	AGV01	go_to	17	completed	2026-06-05 11:40:40.868692+07	2026-06-05 11:40:40.868692+07	2026-06-05 11:41:17.782179+07	lifecycle:picking:confirmed	mq0frrtmeokfqkpy6vq	A06
1450	4f2c770b	AGV01	go_to	13	completed	2026-06-04 10:06:59.076736+07	2026-06-04 10:07:05.401247+07	2026-06-04 10:07:13.405178+07		\N	bounce_retry
1572	b6ddc170	AGV02	go_charge	\N	completed	2026-06-05 09:06:44.490269+07	2026-06-05 09:06:52.462663+07	2026-06-05 09:07:17.410508+07	charge_arrived	mq0a95fhi9ykglumtbf	A06
1452	698c8f84	AGV01	go_to	13	completed	2026-06-04 10:07:13.423132+07	2026-06-04 10:07:29.824439+07	2026-06-04 10:09:07.384311+07	lifecycle:picking:confirmed	\N	bounce_retry
1499	25ac7b5f	AGV01	go_charge	\N	completed	2026-06-04 15:16:46.347762+07	2026-06-04 15:16:54.018198+07	2026-06-04 15:17:18.020566+07	charge_arrived	mpz81aw7qwe11hy3jw	A06
1501	a3f1efa7	AGV01	go_to	18	completed	2026-06-04 15:17:59.385864+07	2026-06-04 15:18:46.386456+07	2026-06-04 15:18:52.230435+07		mpz83dphgq6g7u87m1o	A02
1504	e1b7f4f8	AGV01	go_to	18	completed	2026-06-04 15:18:52.263465+07	2026-06-04 15:19:36.17604+07	2026-06-04 15:19:49.368347+07	lifecycle:picking:confirmed	mpz83dphgq6g7u87m1o	A02
1502	b640e995	AGV01	go_charge	\N	cancelled	2026-06-04 15:17:59.401864+07	2026-06-04 15:19:49.368347+07	2026-06-04 15:20:34.771555+07	force-cancelled by user	mpz83dphgq6g7u87m1o	A02
1505	3170d267	AGV01	go_charge	14	cancelled	2026-06-04 15:20:25.074088+07	\N	2026-06-04 15:20:37.514685+07	cancelled by user	mpz83dphgq6g7u87m1o	A02
1560	e982d32e	AGV02	go_to	17	completed	2026-06-05 09:02:39.61406+07	2026-06-05 09:02:39.61406+07	2026-06-05 09:03:04.338386+07	lifecycle:picking:confirmed	mq0a4k1iw4upmka8qq	A06
1655	30af47d7	AGV02	go_to	64	cancelled	2026-06-05 09:50:14.210656+07	\N	2026-06-05 09:50:15.931243+07	cancelled by user	mq0boupdx7iwru9r66	A06
1569	436cbc03	AGV02	go_to	13	completed	2026-06-05 09:04:11.891804+07	2026-06-05 09:04:22.203228+07	2026-06-05 09:05:03.320572+07	charge_arrived	\N	bounce_retry
1564	7e01f228	AGV01	go_to	17	completed	2026-06-05 09:02:54.992905+07	2026-06-05 09:03:42.185674+07	2026-06-05 09:06:01.189046+07	lifecycle:picking:confirmed	mq0a4vpxw5yohn54xeo	A06
1910	f7150733	AGV02	go_to	64	cancelled	2026-06-05 13:44:43.984308+07	\N	2026-06-05 13:48:50.856967+07	cancelled by user	mq0k525lckpydkmtaes	A06
1653	a6d3f00a	AGV02	go_to	9	cancelled	2026-06-05 09:50:06.760182+07	\N	2026-06-05 09:50:15.931243+07	cancelled by user	mq0boupdx7iwru9r66	A06
1651	87e9942e	AGV02	go_to	10	cancelled	2026-06-05 09:49:59.739136+07	\N	2026-06-05 09:50:15.931243+07	cancelled by user	mq0boupdx7iwru9r66	A06
1654	8ebaa498	AGV01	go_to	4	cancelled	2026-06-05 09:50:13.767072+07	\N	2026-06-05 09:50:23.105533+07	cancelled by user	mq0bolpki3b90cknet	A06
1652	e4ff75d9	AGV01	go_to	64	cancelled	2026-06-05 09:50:00.431847+07	\N	2026-06-05 09:50:23.105533+07	cancelled by user	mq0bolpki3b90cknet	A06
1728	5a8c8fa9	AGV01	go_to	17	completed	2026-06-05 10:32:01.589334+07	2026-06-05 10:32:01.589334+07	2026-06-05 10:32:30.229965+07	lifecycle:picking:confirmed	mq0dbhd5qboylpqny8	A06
1866	4cebaff6	AGV02	go_to	17	completed	2026-06-05 11:42:15.925948+07	2026-06-05 11:42:32.199548+07	2026-06-05 11:42:48.706228+07		mq0fs9zurc4zgiuxnw	A06
1732	5e5e88da	AGV02	go_to	17	completed	2026-06-05 10:32:11.406378+07	2026-06-05 10:32:56.280524+07	2026-06-05 10:33:12.808283+07		mq0dboxe364e9g3q707	A06
1733	854eebc7	AGV02	go_charge	\N	cancelled	2026-06-05 10:32:11.416374+07	\N	2026-06-05 10:41:25.77458+07	cancelled by user	mq0dboxe364e9g3q707	A06
1784	30350929	AGV02	go_to	17	cancelled	2026-06-05 11:17:51.854605+07	\N	2026-06-05 11:25:13.240258+07	cancelled by user	mq0ew3dvswc5dhetxum	A06
1861	3951ddba	AGV02	go_to	17	completed	2026-06-05 11:41:04.41384+07	2026-06-05 11:41:04.41384+07	2026-06-05 11:41:34.432353+07	lifecycle:picking:confirmed	mq0fs9zurc4zgiuxnw	A06
1859	5edc732f	AGV01	go_to	17	completed	2026-06-05 11:40:40.911254+07	2026-06-05 11:41:17.785179+07	2026-06-05 11:41:41.573169+07	lifecycle:picking:confirmed	mq0frrtmeokfqkpy6vq	A06
1862	e6888022	AGV02	go_to	17	completed	2026-06-05 11:41:04.430849+07	2026-06-05 11:41:34.432353+07	2026-06-05 11:42:15.918952+07		mq0fs9zurc4zgiuxnw	A06
1864	5635af62	AGV02	go_to	17	completed	2026-06-05 11:41:34.439352+07	2026-06-05 11:42:15.920064+07	2026-06-05 11:42:32.198574+07		mq0fs9zurc4zgiuxnw	A06
1860	7df8baa7	AGV01	go_charge	\N	cancelled	2026-06-05 11:40:40.919269+07	2026-06-05 11:41:41.574187+07	2026-06-05 11:48:41.675361+07	force-cancelled by user	mq0frrtmeokfqkpy6vq	A06
1868	448fb667	AGV02	go_to	17	cancelled	2026-06-05 11:42:48.719271+07	\N	2026-06-05 11:48:45.635629+07	cancelled by user	mq0fs9zurc4zgiuxnw	A06
1863	a7c9689e	AGV02	go_charge	\N	cancelled	2026-06-05 11:41:04.442365+07	\N	2026-06-05 11:48:45.635629+07	cancelled by user	mq0fs9zurc4zgiuxnw	A06
1943	a25f6496	AGV02	go_charge	\N	cancelled	2026-06-05 14:56:08.591383+07	2026-06-05 14:57:29.85112+07	2026-06-05 15:00:10.027735+07	force-cancelled by user	mq0mr4w13sr8s47b7iq	A06
1942	24ce5264	AGV02	go_to	69	completed	2026-06-05 14:56:08.573389+07	2026-06-05 14:56:40.549018+07	2026-06-05 14:56:55.893384+07		mq0mr4w13sr8s47b7iq	A06
1947	ba776f9e	AGV02	go_to	2	cancelled	2026-06-05 15:00:25.816196+07	\N	2026-06-05 15:36:17.363638+07	cancelled by user	mq0mwgpnrqv2zk3bagp	Sạc Pin
1946	c48f7c7c	AGV02	go_charge	\N	cancelled	2026-06-05 15:00:17.074693+07	\N	2026-06-05 15:36:17.363638+07	cancelled by user	mq0mwgpnrqv2zk3bagp	Sạc Pin
1988	6befc0db	AGV02	go_to	69	completed	2026-06-05 16:20:24.908821+07	2026-06-05 16:20:24.908821+07	2026-06-05 16:23:07.557947+07	lifecycle:picking:confirmed	mq0prigz87ferr8gtgn	A06
1960	99453227	AGV02	go_to	69	completed	2026-06-05 15:54:53.030076+07	2026-06-05 15:55:08.205396+07	2026-06-05 15:55:43.462006+07	lifecycle:picking:confirmed	mq0ou21v1akuscsxc7u	A06
1961	38e2570e	AGV02	go_charge	14	cancelled	2026-06-05 15:56:30.710526+07	2026-06-05 15:56:30.712516+07	2026-06-05 15:57:26.99857+07	force-cancelled by user	mq0ou21v1akuscsxc7u	A06
1990	4a6932c5	AGV02	go_charge	\N	completed	2026-06-05 16:20:25.166669+07	2026-06-05 16:56:43.089666+07	2026-06-05 16:57:30.818568+07	off_route	mq0prigz87ferr8gtgn	A06
2859	11d1f6d9	AGV01	go_charge	\N	completed	2026-06-15 13:16:09.138821+07	2026-06-15 13:16:09.138799+07	2026-06-15 13:16:24.226596+07		mqetl1ogglfgicrv2uf	Sạc Pin
805	826cf71f	AGV01	go_to	9	completed	2026-06-02 10:29:31.549399+07	2026-06-02 10:29:31.549399+07	2026-06-02 10:29:37.764414+07	sim:auto_confirm	508aa13650	Mô phỏng vòng 1/10
806	36b8bc0f	AGV01	go_to	4	completed	2026-06-02 10:29:37.766413+07	2026-06-02 10:29:37.766413+07	2026-06-02 10:29:50.459598+07	sim:auto_confirm	508aa13650	Mô phỏng vòng 1/10
807	002a94e0	AGV01	go_to	4	running	2026-06-02 10:29:50.509257+07	\N	\N	\N	508aa13650	Mô phỏng vòng 2/10
808	4bf8528a	AGV01	go_to	4	failed	2026-06-02 10:29:52.507796+07	2026-06-02 10:29:52.507796+07	2026-06-02 10:29:52.50977+07	AGV01: đã ở tại 4	508aa13650	Mô phỏng vòng 2/10
810	003587fb	AGV01	go_to	4	running	2026-06-02 10:29:56.530623+07	\N	\N	\N	508aa13650	Mô phỏng vòng 2/10
811	2457479a	AGV01	go_to	4	failed	2026-06-02 10:29:58.541835+07	2026-06-02 10:29:58.541835+07	2026-06-02 10:29:58.542805+07	AGV01: đã ở tại 4	508aa13650	Mô phỏng vòng 2/10
817	799f6443	AGV01	go_to	4	failed	2026-06-02 10:30:10.578918+07	2026-06-02 10:30:10.578918+07	2026-06-02 10:30:10.5848+07	AGV01: đã ở tại 4	508aa13650	Mô phỏng vòng 2/10
818	68ba5607	AGV01	go_to	4	running	2026-06-02 10:30:12.5953+07	\N	\N	\N	508aa13650	Mô phỏng vòng 2/10
819	91751fa0	AGV01	go_to	4	running	2026-06-02 10:30:14.614647+07	\N	\N	\N	508aa13650	Mô phỏng vòng 2/10
820	b772ec81	AGV01	go_to	4	failed	2026-06-02 10:30:16.627071+07	2026-06-02 10:30:16.627071+07	2026-06-02 10:30:16.62928+07	AGV01: đã ở tại 4	508aa13650	Mô phỏng vòng 2/10
824	dcfa48c2	AGV01	go_to	4	running	2026-06-02 10:30:24.654304+07	\N	\N	\N	508aa13650	Mô phỏng vòng 2/10
825	70b718c8	AGV01	go_to	4	failed	2026-06-02 10:30:26.673371+07	2026-06-02 10:30:26.673371+07	2026-06-02 10:30:26.674369+07	AGV01: đã ở tại 4	508aa13650	Mô phỏng vòng 2/10
831	65e5d075	AGV01	go_to	4	running	2026-06-02 10:30:38.733511+07	\N	\N	\N	508aa13650	Mô phỏng vòng 2/10
835	1decd75b	AGV01	go_to	6	completed	2026-06-02 10:32:04.577561+07	2026-06-02 10:32:04.577561+07	2026-06-02 10:32:17.23084+07	sim:auto_confirm	73bf900c82	Mô phỏng vòng 1/10
836	71fc0d02	AGV01	go_to	7	completed	2026-06-02 10:32:17.232843+07	2026-06-02 10:32:17.232843+07	2026-06-02 10:32:29.853732+07	sim:auto_confirm	73bf900c82	Mô phỏng vòng 1/10
837	f4a4f58d	AGV01	go_to	9	running	2026-06-02 10:32:29.853732+07	\N	\N	\N	73bf900c82	Mô phỏng vòng 1/10
1736	654dbade	AGV02	go_charge	\N	cancelled	2026-06-05 10:41:53.700765+07	2026-06-05 10:41:53.700765+07	2026-06-05 10:42:00.574429+07	force-cancelled by user	mq0do68q7oovig9b2sa	Sạc Pin
1278	cabcd110	AGV01	go_charge	\N	cancelled	2026-06-03 16:41:32.936234+07	2026-06-03 16:41:38.146623+07	2026-06-03 16:47:46.434838+07	force-cancelled by user	mpxvlt1eo8wkq5ur75	A06
1277	13da24c4	AGV02	go_to	19	cancelled	2026-06-03 16:41:19.933915+07	\N	2026-06-03 16:47:50.355659+07	cancelled by user	mpxvm4anj269exs3y3	A06
1377	9400bb3b	AGV01	go_charge	\N	cancelled	2026-06-04 08:54:49.743713+07	2026-06-04 08:54:49.743713+07	2026-06-04 08:55:00.250705+07	force-cancelled by user	mpyuemtmvypp2ln16u	Sạc Pin
1379	e161e228	AGV02	go_charge	\N	running	2026-06-04 08:55:08.682048+07	2026-06-04 08:55:14.289612+07	\N		mpyuf1f2esznbmckk5g	Sạc Pin
1458	b04fc5e0	AGV01	go_charge	\N	queued	2026-06-04 10:24:42.974639+07	\N	\N	\N	mpyxm88lr60uxwl8rk	A06
1453	3fc73274	AGV02	go_to	17	completed	2026-06-04 10:24:31.490827+07	2026-06-04 10:24:31.490827+07	2026-06-04 10:24:58.560636+07	lifecycle:picking:confirmed	mpyxlzeekupi70eumyf	A06
1457	c520bc0d	AGV01	go_to	17	running	2026-06-04 10:24:42.962418+07	2026-06-04 10:25:23.877155+07	\N		mpyxm88lr60uxwl8rk	A06
1506	ced6acbc	AGV01	go_to	18	cancelled	2026-06-04 15:48:13.779346+07	2026-06-04 15:48:13.779346+07	2026-06-04 15:53:56.329749+07	force-cancelled by user	mpz969q852xh5uw5sx	A02
1561	8edc1203	AGV02	go_to	17	completed	2026-06-05 09:02:39.808738+07	2026-06-05 09:03:04.338386+07	2026-06-05 09:03:31.199284+07	lifecycle:picking:confirmed	mq0a4k1iw4upmka8qq	A06
1563	1f195e34	AGV01	go_to	17	completed	2026-06-05 09:02:54.749329+07	2026-06-05 09:02:54.749329+07	2026-06-05 09:03:42.184634+07	lifecycle:picking:confirmed	mq0a4vpxw5yohn54xeo	A06
1562	b111925a	AGV02	go_charge	\N	completed	2026-06-05 09:02:39.824709+07	2026-06-05 09:03:31.200283+07	2026-06-05 09:03:42.455685+07		mq0a4k1iw4upmka8qq	A06
1567	85ccfc89	AGV02	go_charge	\N	completed	2026-06-05 09:03:54.550545+07	2026-06-05 09:03:54.550545+07	2026-06-05 09:04:11.864753+07		\N	bounce_retry
1571	07bc9f15	AGV02	go_charge	\N	completed	2026-06-05 09:06:13.98847+07	2026-06-05 09:06:44.468255+07	2026-06-05 09:06:52.456647+07		mq0a95fhi9ykglumtbf	A06
1656	215a2d21	AGV01	go_charge	\N	completed	2026-06-05 09:51:26.663204+07	2026-06-05 09:51:26.663204+07	2026-06-05 09:51:26.890453+07	bounce_wait	mq0bvakg0qnzw1jn8g5c	Sạc Pin
1787	7daa1a2d	AGV01	go_charge	\N	cancelled	2026-06-05 11:25:42.998719+07	2026-06-05 11:25:42.998719+07	2026-06-05 11:25:50.16103+07	force-cancelled by user	mq0f8j0yl5cabwocuf	Sạc Pin
1731	15193770	AGV02	go_to	17	completed	2026-06-05 10:32:11.382265+07	2026-06-05 10:32:11.382265+07	2026-06-05 10:32:56.279519+07	lifecycle:picking:confirmed	mq0dboxe364e9g3q707	A06
1786	db12a122	AGV02	go_charge	\N	cancelled	2026-06-05 11:25:27.092293+07	\N	2026-06-05 11:25:54.812533+07	cancelled by user	mq0f86lwjndamoe35m8	Sạc Pin
1729	2a08c092	AGV01	go_to	17	completed	2026-06-05 10:32:01.630892+07	2026-06-05 10:32:30.230963+07	2026-06-05 10:33:03.788904+07	lifecycle:picking:confirmed	mq0dbhd5qboylpqny8	A06
1785	9f7434ac	AGV02	go_charge	\N	cancelled	2026-06-05 11:25:26.907473+07	2026-06-05 11:25:26.907473+07	2026-06-05 11:25:54.811537+07	force-cancelled by user	mq0f86lwjndamoe35m8	Sạc Pin
1734	36b6a5c4	AGV02	go_to	17	cancelled	2026-06-05 10:32:56.295065+07	2026-06-05 10:33:12.80928+07	2026-06-05 10:41:25.767579+07	force-cancelled by user	mq0dboxe364e9g3q707	A06
1730	4bd74ee3	AGV01	go_charge	\N	cancelled	2026-06-05 10:32:01.64491+07	2026-06-05 10:33:03.789806+07	2026-06-05 10:41:44.241038+07	force-cancelled by user	mq0dbhd5qboylpqny8	A06
1915	98867d7b	AGV02	go_to	17	completed	2026-06-05 13:58:32.765461+07	2026-06-05 13:59:05.995245+07	2026-06-05 13:59:47.766438+07		mq0kp2g6y1jfwj5fq7p	A06
1865	6b15e42e	AGV01	go_charge	\N	cancelled	2026-06-05 11:41:41.59119+07	\N	2026-06-05 11:48:41.676359+07	cancelled by user	mq0frrtmeokfqkpy6vq	A06
1867	424157fd	AGV02	go_to	17	cancelled	2026-06-05 11:42:32.206547+07	2026-06-05 11:42:48.706228+07	2026-06-05 11:48:45.635629+07	force-cancelled by user	mq0fs9zurc4zgiuxnw	A06
1911	de078125	AGV01	go_to	17	completed	2026-06-05 13:58:14.826768+07	2026-06-05 13:58:14.826768+07	2026-06-05 13:58:48.830986+07	lifecycle:picking:confirmed	mq0koom8exeq5hkxgx	A06
1921	4dfc5c78	AGV02	go_to	17	completed	2026-06-05 14:01:40.158346+07	2026-06-05 14:01:40.158346+07	2026-06-05 14:02:08.29363+07	lifecycle:picking:confirmed	mq0kt321uakrafem32	A06
1931	f666dcec	AGV02	go_charge	\N	completed	2026-06-05 14:06:19.278046+07	2026-06-05 14:06:19.278046+07	2026-06-05 14:06:26.301227+07	off_route	\N	bounce_retry
1925	b406a32c	AGV01	go_to	17	cancelled	2026-06-05 14:01:49.485184+07	2026-06-05 14:02:32.196522+07	2026-06-05 14:06:04.212692+07	force-cancelled by user	mq0kta5chrlenp08cs	A06
1917	d601e99a	AGV02	go_to	17	completed	2026-06-05 13:59:06.004621+07	2026-06-05 13:59:47.76754+07	2026-06-05 14:00:21.339057+07	lifecycle:picking:confirmed	mq0kp2g6y1jfwj5fq7p	A06
1926	adb654b8	AGV01	go_charge	\N	cancelled	2026-06-05 14:01:49.502178+07	\N	2026-06-05 14:06:04.212692+07	cancelled by user	mq0kta5chrlenp08cs	A06
1919	a182a83b	AGV01	go_charge	\N	completed	2026-06-05 13:59:16.828279+07	2026-06-05 13:59:32.251738+07	2026-06-05 14:00:27.84052+07	charge_arrived	\N	bounce_retry
1916	857eb971	AGV02	go_charge	\N	completed	2026-06-05 13:58:32.810192+07	2026-06-05 14:00:21.340058+07	2026-06-05 14:00:36.055012+07		mq0kp2g6y1jfwj5fq7p	A06
1932	83b7d9f4	AGV02	go_charge	13	completed	2026-06-05 14:06:26.300184+07	2026-06-05 14:06:26.302235+07	2026-06-05 14:06:40.893325+07		\N	bounce_retry
1945	46816ee1	AGV02	go_charge	\N	cancelled	2026-06-05 15:00:17.058684+07	2026-06-05 15:00:17.058684+07	2026-06-05 15:36:17.36264+07	force-cancelled by user	mq0mwgpnrqv2zk3bagp	Sạc Pin
1944	d8f30a6c	AGV02	go_to	69	completed	2026-06-05 14:56:40.725651+07	2026-06-05 14:56:55.895396+07	2026-06-05 14:57:29.850116+07	lifecycle:picking:confirmed	mq0mr4w13sr8s47b7iq	A06
1963	0a7cecb6	AGV02	go_to	2	cancelled	2026-06-05 15:56:41.656358+07	\N	2026-06-05 15:57:26.999574+07	cancelled by user	mq0ou21v1akuscsxc7u	A06
1962	4a1919ad	AGV02	go_charge	\N	cancelled	2026-06-05 15:56:30.859707+07	\N	2026-06-05 15:57:26.999574+07	cancelled by user	mq0ou21v1akuscsxc7u	A06
1964	15d69e3e	AGV02	go_to	69	completed	2026-06-05 15:58:30.913576+07	2026-06-05 15:58:30.913576+07	2026-06-05 15:59:01.121678+07	lifecycle:picking:confirmed	mq0ozclas3up3vfyj4q	A02
1989	6a33ff43	AGV02	go_to	69	completed	2026-06-05 16:20:25.148691+07	2026-06-05 16:23:07.557947+07	2026-06-05 16:23:25.501932+07		mq0prigz87ferr8gtgn	A06
809	ca16158c	AGV01	go_to	4	failed	2026-06-02 10:29:54.513102+07	2026-06-02 10:29:54.513102+07	2026-06-02 10:29:54.515101+07	AGV01: đã ở tại 4	508aa13650	Mô phỏng vòng 2/10
812	318d9301	AGV01	go_to	4	running	2026-06-02 10:30:00.546092+07	\N	\N	\N	508aa13650	Mô phỏng vòng 2/10
813	17869b96	AGV01	go_to	4	running	2026-06-02 10:30:02.558167+07	\N	\N	\N	508aa13650	Mô phỏng vòng 2/10
814	c0faa1ff	AGV01	go_to	4	running	2026-06-02 10:30:04.568606+07	\N	\N	\N	508aa13650	Mô phỏng vòng 2/10
815	e328aae8	AGV01	go_to	4	running	2026-06-02 10:30:06.565173+07	\N	\N	\N	508aa13650	Mô phỏng vòng 2/10
816	4f87769f	AGV01	go_to	4	failed	2026-06-02 10:30:08.581258+07	2026-06-02 10:30:08.581258+07	2026-06-02 10:30:08.582259+07	AGV01: đã ở tại 4	508aa13650	Mô phỏng vòng 2/10
821	89a9deb5	AGV01	go_to	4	running	2026-06-02 10:30:18.636021+07	\N	\N	\N	508aa13650	Mô phỏng vòng 2/10
822	00afde40	AGV01	go_to	4	running	2026-06-02 10:30:20.642806+07	\N	\N	\N	508aa13650	Mô phỏng vòng 2/10
823	5b4cbd17	AGV01	go_to	4	failed	2026-06-02 10:30:22.649902+07	2026-06-02 10:30:22.649902+07	2026-06-02 10:30:22.65292+07	AGV01: đã ở tại 4	508aa13650	Mô phỏng vòng 2/10
826	d5e568ce	AGV01	go_to	4	failed	2026-06-02 10:30:28.66969+07	\N	\N	\N	508aa13650	Mô phỏng vòng 2/10
827	71db6188	AGV01	go_to	4	failed	2026-06-02 10:30:30.69412+07	2026-06-02 10:30:30.69412+07	2026-06-02 10:30:30.698056+07	AGV01: đã ở tại 4	508aa13650	Mô phỏng vòng 2/10
828	d7590f7f	AGV01	go_to	4	failed	2026-06-02 10:30:32.706212+07	\N	\N	\N	508aa13650	Mô phỏng vòng 2/10
829	bdcdd107	AGV01	go_to	4	running	2026-06-02 10:30:34.722269+07	\N	\N	\N	508aa13650	Mô phỏng vòng 2/10
830	00ae5775	AGV01	go_to	4	failed	2026-06-02 10:30:36.745752+07	2026-06-02 10:30:36.745752+07	2026-06-02 10:30:36.746736+07	AGV01: đã ở tại 4	508aa13650	Mô phỏng vòng 2/10
832	70c5e949	AGV01	go_to	4	running	2026-06-02 10:30:40.758556+07	\N	\N	\N	508aa13650	Mô phỏng vòng 2/10
833	3e368be3	AGV01	go_to	4	failed	2026-06-02 10:30:42.762861+07	\N	\N	\N	508aa13650	Mô phỏng vòng 2/10
834	6840cd2b	AGV01	go_to	4	completed	2026-06-02 10:31:52.978044+07	2026-06-02 10:31:52.978044+07	2026-06-02 10:32:04.576635+07	sim:auto_confirm	73bf900c82	Mô phỏng vòng 1/10
838	dec0dcf7	AGV01	go_to	17	completed	2026-06-02 13:19:42.806231+07	2026-06-02 13:19:42.806231+07	2026-06-02 13:20:18.236178+07	lifecycle:picking:confirmed	mpw8zkmz2v76lfewvlz	A06
853	ed5d5155	AGV01	go_to	4	failed	2026-06-02 13:28:02.441188+07	2026-06-02 13:28:02.441188+07	2026-06-02 13:28:02.442184+07	AGV01: đã ở tại 4	8d60a418c0	Mô phỏng vòng 2/10
839	e1967b3c	AGV01	go_to	17	completed	2026-06-02 13:19:42.85397+07	2026-06-02 13:20:18.236178+07	2026-06-02 13:20:35.68825+07	lifecycle:picking:confirmed	mpw8zkmz2v76lfewvlz	A06
840	0c61d87a	AGV01	go_charge	\N	completed	2026-06-02 13:19:42.869543+07	2026-06-02 13:20:35.692244+07	2026-06-02 13:20:41.015687+07		mpw8zkmz2v76lfewvlz	A06
854	9f75d38b	AGV01	go_to	4	failed	2026-06-02 13:28:04.477375+07	2026-06-02 13:28:04.477375+07	2026-06-02 13:28:04.490271+07	AGV01: đã ở tại 4	8d60a418c0	Mô phỏng vòng 2/10
841	26bfb53b	AGV01	go_charge	\N	completed	2026-06-02 13:20:35.834267+07	2026-06-02 13:20:41.016687+07	2026-06-02 13:21:27.354064+07	charge_arrived	mpw8zkmz2v76lfewvlz	A06
842	452c1916	AGV01	go_to	19	completed	2026-06-02 13:23:32.136153+07	2026-06-02 13:23:32.136153+07	2026-06-02 13:24:04.552111+07	lifecycle:picking:confirmed	mpw94hlvmrq4pfw3mb	A03
843	25d1e041	AGV01	go_charge	\N	completed	2026-06-02 13:23:32.17328+07	2026-06-02 13:24:04.553105+07	2026-06-02 13:24:13.249316+07		mpw94hlvmrq4pfw3mb	A03
855	37bdded5	AGV01	go_to	4	failed	2026-06-02 13:28:06.502904+07	2026-06-02 13:28:06.502904+07	2026-06-02 13:28:06.503905+07	AGV01: đã ở tại 4	8d60a418c0	Mô phỏng vòng 2/10
844	2dc06087	AGV01	go_charge	\N	completed	2026-06-02 13:24:04.587649+07	2026-06-02 13:24:13.250311+07	2026-06-02 13:24:58.892351+07	charge_arrived	mpw94hlvmrq4pfw3mb	A03
845	c11d81ca	AGV01	go_to	4	completed	2026-06-02 13:26:29.003354+07	2026-06-02 13:26:29.003354+07	2026-06-02 13:26:38.14523+07	sim:auto_confirm	8d60a418c0	Mô phỏng vòng 1/10
846	cd387778	AGV01	go_to	6	completed	2026-06-02 13:26:38.14574+07	2026-06-02 13:26:38.14574+07	2026-06-02 13:26:50.976094+07	sim:auto_confirm	8d60a418c0	Mô phỏng vòng 1/10
847	ea18fe88	AGV01	go_to	7	completed	2026-06-02 13:26:50.979092+07	2026-06-02 13:26:50.979092+07	2026-06-02 13:27:05.762212+07	sim:auto_confirm	8d60a418c0	Mô phỏng vòng 1/10
848	5cc3790a	AGV01	go_to	9	completed	2026-06-02 13:27:03.743584+07	2026-06-02 13:27:05.763215+07	2026-06-02 13:27:43.289203+07	sim:auto_confirm	8d60a418c0	Mô phỏng vòng 1/10
849	77f93740	AGV01	go_to	4	completed	2026-06-02 13:27:43.290212+07	2026-06-02 13:27:43.290212+07	2026-06-02 13:27:56.408664+07	sim:auto_confirm	8d60a418c0	Mô phỏng vòng 1/10
850	4c56ef1e	AGV01	go_to	4	running	2026-06-02 13:27:56.410677+07	\N	\N	\N	8d60a418c0	Mô phỏng vòng 2/10
851	f5eec21e	AGV01	go_to	4	running	2026-06-02 13:27:58.4133+07	\N	\N	\N	8d60a418c0	Mô phỏng vòng 2/10
852	55b23e4b	AGV01	go_to	4	failed	2026-06-02 13:28:00.43381+07	2026-06-02 13:28:00.43381+07	2026-06-02 13:28:00.434822+07	AGV01: đã ở tại 4	8d60a418c0	Mô phỏng vòng 2/10
856	a2565841	AGV01	go_to	4	failed	2026-06-02 13:28:08.504396+07	2026-06-02 13:28:08.504396+07	2026-06-02 13:28:08.5054+07	AGV01: đã ở tại 4	8d60a418c0	Mô phỏng vòng 2/10
857	dc4a5ffb	AGV01	go_to	4	failed	2026-06-02 13:28:10.522503+07	2026-06-02 13:28:10.522503+07	2026-06-02 13:28:10.524627+07	AGV01: đã ở tại 4	8d60a418c0	Mô phỏng vòng 2/10
858	cecc379a	AGV01	go_to	4	running	2026-06-02 13:28:12.530834+07	\N	\N	\N	8d60a418c0	Mô phỏng vòng 2/10
859	d8eacb95	AGV01	go_to	4	failed	2026-06-02 13:28:14.512677+07	2026-06-02 13:28:14.512677+07	2026-06-02 13:28:14.513636+07	AGV01: đã ở tại 4	8d60a418c0	Mô phỏng vòng 2/10
860	609309f1	AGV01	go_to	4	failed	2026-06-02 13:28:16.532816+07	2026-06-02 13:28:16.532816+07	2026-06-02 13:28:16.533694+07	AGV01: đã ở tại 4	8d60a418c0	Mô phỏng vòng 2/10
861	28f84d61	AGV01	go_to	4	running	2026-06-02 13:28:18.555715+07	\N	\N	\N	8d60a418c0	Mô phỏng vòng 2/10
862	b3107616	AGV01	go_to	4	running	2026-06-02 13:28:20.560943+07	\N	\N	\N	8d60a418c0	Mô phỏng vòng 2/10
863	9f35e6ab	AGV01	go_to	4	running	2026-06-02 13:28:22.58424+07	\N	\N	\N	8d60a418c0	Mô phỏng vòng 2/10
864	bfef76ce	AGV01	go_to	4	running	2026-06-02 13:28:24.593066+07	\N	\N	\N	8d60a418c0	Mô phỏng vòng 2/10
865	d6e87fd6	AGV01	go_to	4	running	2026-06-02 13:28:26.610928+07	\N	\N	\N	8d60a418c0	Mô phỏng vòng 2/10
866	ee6b4521	AGV01	go_to	4	failed	2026-06-02 13:28:28.626725+07	\N	\N	\N	8d60a418c0	Mô phỏng vòng 2/10
867	b2571460	AGV01	go_to	4	running	2026-06-02 13:28:30.63427+07	\N	\N	\N	8d60a418c0	Mô phỏng vòng 2/10
868	d2d249f6	AGV01	go_to	4	running	2026-06-02 13:28:32.625556+07	\N	\N	\N	8d60a418c0	Mô phỏng vòng 2/10
869	46a98d03	AGV01	go_to	4	failed	2026-06-02 13:28:34.635582+07	2026-06-02 13:28:34.635582+07	2026-06-02 13:28:34.636565+07	AGV01: đã ở tại 4	8d60a418c0	Mô phỏng vòng 2/10
870	08fb5d20	AGV01	go_to	4	running	2026-06-02 13:28:36.628557+07	\N	\N	\N	8d60a418c0	Mô phỏng vòng 2/10
871	fdd3b7d5	AGV01	go_to	4	failed	2026-06-02 13:28:38.647583+07	\N	\N	\N	8d60a418c0	Mô phỏng vòng 2/10
872	40936b9b	AGV01	go_to	4	failed	2026-06-02 13:28:40.666189+07	\N	\N	\N	8d60a418c0	Mô phỏng vòng 2/10
873	77ede008	AGV01	go_to	4	failed	2026-06-02 13:28:42.690113+07	\N	\N	\N	8d60a418c0	Mô phỏng vòng 2/10
874	173b7b47	AGV01	go_to	4	running	2026-06-02 13:28:44.708515+07	\N	\N	\N	8d60a418c0	Mô phỏng vòng 2/10
875	79dbbf55	AGV01	go_to	4	failed	2026-06-02 13:28:46.722084+07	\N	\N	\N	8d60a418c0	Mô phỏng vòng 2/10
876	590162c1	AGV01	go_to	1	completed	2026-06-02 13:33:35.698501+07	2026-06-02 13:33:35.698501+07	2026-06-02 13:33:43.819739+07	sim:auto_confirm	3c5950d98d	Mô phỏng vòng 1/10
2789	1038fd7b	AGV01	go_charge	\N	completed	2026-06-15 10:55:25.983288+07	2026-06-15 10:55:41.134862+07	2026-06-15 10:56:00.022903+07	yield_siding	mqeoijy2p8n8127dea	A06
877	a7d9455b	AGV01	go_to	17	cancelled	2026-06-02 13:33:43.82188+07	2026-06-02 13:33:43.82188+07	2026-06-02 13:33:57.200705+07	force-cancelled by user	3c5950d98d	Mô phỏng vòng 1/10
878	7d5d9f3f	AGV01	go_to	17	cancelled	2026-06-02 13:33:43.963304+07	\N	2026-06-02 13:33:57.200705+07	cancelled by user	3c5950d98d	Mô phỏng vòng 1/10
879	893fdf25	AGV01	go_to	17	completed	2026-06-02 13:54:36.669153+07	2026-06-02 13:54:36.669153+07	2026-06-02 13:55:06.506214+07	lifecycle:picking:confirmed	mpwa8ga7j5er2lojj5j	A06
910	1e583529	AGV01	go_to	17	completed	2026-06-02 14:07:53.908388+07	2026-06-02 14:07:53.908388+07	2026-06-02 14:08:09.682344+07	sim:auto_confirm	e6a22a7386	Mô phỏng vòng 1/10
911	eeff5439	AGV01	go_to	19	cancelled	2026-06-02 14:08:09.683332+07	2026-06-02 14:08:09.683332+07	2026-06-02 14:09:14.744455+07	force-cancelled by user	e6a22a7386	Mô phỏng vòng 2/10
880	28c2d6d6	AGV01	go_to	17	completed	2026-06-02 13:54:36.709646+07	2026-06-02 13:55:06.506214+07	2026-06-02 13:55:23.679024+07	lifecycle:picking:confirmed	mpwa8ga7j5er2lojj5j	A06
881	dabde1cd	AGV01	go_charge	\N	completed	2026-06-02 13:54:36.722348+07	2026-06-02 13:55:23.68003+07	2026-06-02 13:55:28.897724+07		mpwa8ga7j5er2lojj5j	A06
882	e9fdbaf7	AGV01	go_charge	\N	completed	2026-06-02 13:55:23.704216+07	2026-06-02 13:55:28.902243+07	2026-06-02 13:56:09.565782+07	charge_arrived	mpwa8ga7j5er2lojj5j	A06
883	efb8900f	AGV01	go_to	1	completed	2026-06-02 13:56:45.22089+07	2026-06-02 13:56:45.22089+07	2026-06-02 13:56:52.829578+07	sim:auto_confirm	1918b84de3	Mô phỏng vòng 1/10
884	4d2176c9	AGV01	go_to	17	cancelled	2026-06-02 13:56:52.831103+07	2026-06-02 13:56:52.831103+07	2026-06-02 13:59:03.862167+07	force-cancelled by user	1918b84de3	Mô phỏng vòng 1/10
885	07b8f1d6	AGV01	go_to	17	cancelled	2026-06-02 13:56:52.855801+07	\N	2026-06-02 13:59:03.862167+07	cancelled by user	1918b84de3	Mô phỏng vòng 1/10
886	71880072	AGV01	go_to	1	completed	2026-06-02 14:03:32.358632+07	2026-06-02 14:03:32.358632+07	2026-06-02 14:03:40.479197+07	sim:auto_confirm	69c2c801ca	Mô phỏng vòng 1/10
888	ec1f5b60	AGV01	go_to	17	cancelled	2026-06-02 14:03:40.634077+07	\N	2026-06-02 14:05:24.152838+07	cancelled by user	69c2c801ca	Mô phỏng vòng 1/10
887	8bcc1ff5	AGV01	go_to	17	cancelled	2026-06-02 14:03:40.480143+07	2026-06-02 14:03:40.480143+07	2026-06-02 14:05:24.145837+07	force-cancelled by user	69c2c801ca	Mô phỏng vòng 1/10
889	b5a35c80	AGV01	go_to	3	failed	2026-06-02 14:06:38.471155+07	2026-06-02 14:06:38.471155+07	2026-06-02 14:06:38.471155+07	AGV01: đã ở tại 3	45e242f235	Mô phỏng vòng 1/10
890	37c824eb	AGV01	go_to	3	failed	2026-06-02 14:06:40.495639+07	\N	\N	\N	45e242f235	Mô phỏng vòng 1/10
891	c7efe071	AGV01	go_to	3	failed	2026-06-02 14:06:42.55518+07	2026-06-02 14:06:42.55518+07	2026-06-02 14:06:42.556176+07	AGV01: đã ở tại 3	45e242f235	Mô phỏng vòng 1/10
892	94f30d67	AGV01	go_to	3	running	2026-06-02 14:06:44.552693+07	\N	\N	\N	45e242f235	Mô phỏng vòng 1/10
893	591c0031	AGV01	go_to	3	failed	2026-06-02 14:06:46.600568+07	2026-06-02 14:06:46.600568+07	2026-06-02 14:06:46.612678+07	AGV01: đã ở tại 3	45e242f235	Mô phỏng vòng 1/10
894	3323be05	AGV01	go_to	3	failed	2026-06-02 14:06:48.63803+07	\N	\N	\N	45e242f235	Mô phỏng vòng 1/10
895	92a0756c	AGV01	go_to	3	running	2026-06-02 14:06:50.661868+07	\N	\N	\N	45e242f235	Mô phỏng vòng 1/10
896	0e445545	AGV01	go_to	3	running	2026-06-02 14:06:52.667646+07	\N	\N	\N	45e242f235	Mô phỏng vòng 1/10
897	c1367fb8	AGV01	go_to	3	running	2026-06-02 14:06:54.692573+07	\N	\N	\N	45e242f235	Mô phỏng vòng 1/10
898	a363ced2	AGV01	go_to	3	failed	2026-06-02 14:06:56.702545+07	2026-06-02 14:06:56.702545+07	2026-06-02 14:06:56.703798+07	AGV01: đã ở tại 3	45e242f235	Mô phỏng vòng 1/10
899	93c61e3d	AGV01	go_to	3	running	2026-06-02 14:06:58.728806+07	\N	\N	\N	45e242f235	Mô phỏng vòng 1/10
900	789e1bf8	AGV01	go_to	3	running	2026-06-02 14:07:00.723398+07	\N	\N	\N	45e242f235	Mô phỏng vòng 1/10
901	b403369a	AGV01	go_to	3	failed	2026-06-02 14:07:02.739074+07	2026-06-02 14:07:02.739074+07	2026-06-02 14:07:02.73996+07	AGV01: đã ở tại 3	45e242f235	Mô phỏng vòng 1/10
902	86950a09	AGV01	go_to	3	failed	2026-06-02 14:07:04.739234+07	2026-06-02 14:07:04.739234+07	2026-06-02 14:07:04.740229+07	AGV01: đã ở tại 3	45e242f235	Mô phỏng vòng 1/10
903	a42361e6	AGV01	go_to	3	failed	2026-06-02 14:07:06.752552+07	2026-06-02 14:07:06.752552+07	2026-06-02 14:07:06.753566+07	AGV01: đã ở tại 3	45e242f235	Mô phỏng vòng 1/10
904	e03415dd	AGV01	go_to	3	failed	2026-06-02 14:07:08.768534+07	\N	\N	\N	45e242f235	Mô phỏng vòng 1/10
905	03fafdf8	AGV01	go_to	3	running	2026-06-02 14:07:10.771512+07	\N	\N	\N	45e242f235	Mô phỏng vòng 1/10
906	cde38262	AGV01	go_to	3	running	2026-06-02 14:07:12.782825+07	\N	\N	\N	45e242f235	Mô phỏng vòng 1/10
907	41904e03	AGV01	go_to	3	running	2026-06-02 14:07:14.792307+07	\N	\N	\N	45e242f235	Mô phỏng vòng 1/10
908	1515439a	AGV01	go_to	3	failed	2026-06-02 14:07:16.812737+07	2026-06-02 14:07:16.812737+07	2026-06-02 14:07:16.813714+07	AGV01: đã ở tại 3	45e242f235	Mô phỏng vòng 1/10
909	49d5411c	AGV01	go_to	19	completed	2026-06-02 14:07:44.321397+07	2026-06-02 14:07:44.321397+07	2026-06-02 14:07:53.907389+07	sim:auto_confirm	e6a22a7386	Mô phỏng vòng 1/10
912	622a348e	AGV01	go_charge	\N	cancelled	2026-06-02 14:09:24.744158+07	2026-06-02 14:09:24.744158+07	2026-06-02 14:09:45.022357+07	force-cancelled by user	mpwarhj4k0hs62d99r	Sạc Pin
914	d83aa03d	AGV01	go_charge	\N	cancelled	2026-06-02 14:10:34.092778+07	\N	2026-06-02 14:10:47.482557+07	cancelled by user	mpwasz0x0wvrmiiyas5	Sạc Pin
913	24271db6	AGV01	go_charge	\N	cancelled	2026-06-02 14:10:34.070648+07	2026-06-02 14:10:34.070648+07	2026-06-02 14:10:47.481506+07	force-cancelled by user	mpwasz0x0wvrmiiyas5	Sạc Pin
915	5b73e076	AGV01	go_to	17	cancelled	2026-06-02 14:15:41.395084+07	2026-06-02 14:15:41.395084+07	2026-06-02 14:15:57.58144+07	force-cancelled by user	e6a22a7386	Mô phỏng vòng 2/10
916	5f413dea	AGV01	go_charge	\N	completed	2026-06-02 14:16:09.603592+07	2026-06-02 14:16:09.603592+07	2026-06-02 14:16:35.542789+07	charge_arrived	mpwb05x9izii01oqdm	Sạc Pin
917	27161240	AGV01	go_to	1	completed	2026-06-02 14:20:09.358323+07	2026-06-02 14:20:09.358323+07	2026-06-02 14:20:16.963549+07	sim:auto_confirm	a6b36e9f21	Mô phỏng vòng 1/10
919	6e84e86c	AGV01	go_to	17	cancelled	2026-06-02 14:20:17.136744+07	\N	2026-06-02 14:20:40.622324+07	cancelled by user	a6b36e9f21	Mô phỏng vòng 1/10
918	3a0bf07a	AGV01	go_to	17	cancelled	2026-06-02 14:20:16.97119+07	2026-06-02 14:20:16.97119+07	2026-06-02 14:20:40.622324+07	force-cancelled by user	a6b36e9f21	Mô phỏng vòng 1/10
920	b93c2253	AGV01	go_to	3	completed	2026-06-02 14:21:38.241821+07	2026-06-02 14:21:38.241821+07	2026-06-02 14:21:47.318663+07	sim:auto_confirm	3a898c8756	Mô phỏng vòng 1/10
921	717ea528	AGV01	go_to	17	completed	2026-06-02 14:21:47.319654+07	2026-06-02 14:21:47.319654+07	2026-06-02 14:21:47.505197+07	sim:auto_confirm	3a898c8756	Mô phỏng vòng 1/10
924	55f51b3f	AGV01	go_to	1	completed	2026-06-02 14:22:10.83174+07	2026-06-02 14:22:10.83174+07	2026-06-02 14:22:12.297822+07	sim:auto_confirm	a6b36e9f21	Mô phỏng vòng 2/10
922	ebea9c6a	AGV01	go_to	17	completed	2026-06-02 14:21:47.326879+07	2026-06-02 14:21:47.505197+07	2026-06-02 14:21:56.50401+07	sim:auto_confirm	3a898c8756	Mô phỏng vòng 1/10
926	29eb3f14	AGV01	go_to	3	cancelled	2026-06-02 14:22:12.300027+07	2026-06-02 14:22:12.359496+07	2026-06-02 14:23:39.705845+07	force-cancelled by user	3a898c8756	Mô phỏng vòng 2/10
923	fbd62965	AGV01	go_to	17	completed	2026-06-02 14:21:47.510181+07	2026-06-02 14:21:56.50401+07	2026-06-02 14:21:56.61258+07	sim:auto_confirm	3a898c8756	Mô phỏng vòng 1/10
925	f0bd4337	AGV01	go_to	1	completed	2026-06-02 14:22:10.841014+07	2026-06-02 14:22:12.297822+07	2026-06-02 14:22:12.359496+07	sim:auto_confirm	a6b36e9f21	Mô phỏng vòng 2/10
929	63f45178	AGV01	go_to	3	completed	2026-06-02 14:33:12.957488+07	2026-06-02 14:33:12.957488+07	2026-06-02 14:33:22.543173+07	sim:auto_confirm	bd79e0ef88	Mô phỏng vòng 1/10
927	3a86cc92	AGV01	go_to	3	cancelled	2026-06-02 14:22:12.36865+07	\N	2026-06-02 14:23:39.711378+07	cancelled by user	3a898c8756	Mô phỏng vòng 2/10
928	0a2ffe9f	AGV01	go_to	1	cancelled	2026-06-02 14:22:12.412719+07	\N	2026-06-02 14:23:39.711378+07	cancelled by user	3a898c8756	Mô phỏng vòng 2/10
930	1724ccee	AGV01	go_to	17	completed	2026-06-02 14:33:23.353907+07	2026-06-02 14:33:23.353907+07	2026-06-02 14:33:32.539619+07	sim:auto_confirm	bd79e0ef88	Mô phỏng vòng 1/10
931	b1e79e87	AGV01	go_to	17	completed	2026-06-02 14:33:23.363043+07	2026-06-02 14:33:32.54069+07	2026-06-02 14:33:48.258016+07	sim:auto_confirm	bd79e0ef88	Mô phỏng vòng 1/10
932	59ff634e	AGV01	go_to	3	cancelled	2026-06-02 14:33:49.076132+07	2026-06-02 14:33:49.076132+07	2026-06-02 14:34:59.193615+07	force-cancelled by user	bd79e0ef88	Mô phỏng vòng 1/10
933	89be6107	AGV01	go_to	3	cancelled	2026-06-02 14:33:49.082126+07	\N	2026-06-02 14:34:59.193615+07	cancelled by user	bd79e0ef88	Mô phỏng vòng 1/10
934	ce7ad9bd	AGV01	go_to	17	completed	2026-06-02 15:11:08.771966+07	2026-06-02 15:11:08.771966+07	2026-06-02 15:11:42.85704+07	lifecycle:picking:confirmed	mpwcyvki2sjuc008qp3	A06
958	d33a006e	AGV02	go_charge	\N	completed	2026-06-02 16:55:51.074313+07	2026-06-02 16:55:51.074313+07	2026-06-02 16:55:52.756723+07	charge_arrived	mpwgpj0ry2q0i49d8q	A06
935	274119b4	AGV01	go_to	17	completed	2026-06-02 15:11:08.807282+07	2026-06-02 15:11:42.883815+07	2026-06-02 15:12:55.44082+07	event:continue	mpwcyvki2sjuc008qp3	A06
936	ffc51bff	AGV01	go_charge	\N	completed	2026-06-02 15:11:08.817281+07	2026-06-02 15:12:55.44082+07	2026-06-02 15:13:02.680153+07		mpwcyvki2sjuc008qp3	A06
941	7e228b2d	AGV01	go_charge	\N	cancelled	2026-06-02 15:12:55.448532+07	2026-06-02 15:13:02.681096+07	2026-06-02 16:29:50.017473+07	force-cancelled by user	mpwcyvki2sjuc008qp3	A06
937	5925385e	AGV02	go_to	16	cancelled	2026-06-02 15:11:24.810583+07	2026-06-02 15:11:24.810583+07	2026-06-02 16:29:55.618826+07	force-cancelled by user	mpwcz7yebfd21vjeux	A06
940	de031742	AGV02	go_to	19	cancelled	2026-06-02 15:11:55.114249+07	\N	2026-06-02 16:29:55.62784+07	cancelled by user	mpwcz7yebfd21vjeux	A06
938	6916c0e0	AGV02	go_to	16	cancelled	2026-06-02 15:11:24.886517+07	\N	2026-06-02 16:29:55.62784+07	cancelled by user	mpwcz7yebfd21vjeux	A06
939	d710d67c	AGV02	go_charge	\N	cancelled	2026-06-02 15:11:24.903814+07	\N	2026-06-02 16:29:55.62784+07	cancelled by user	mpwcz7yebfd21vjeux	A06
942	0e193104	AGV01	go_charge	\N	cancelled	2026-06-02 16:31:54.545226+07	2026-06-02 16:31:54.545226+07	2026-06-02 16:32:01.264476+07	force-cancelled by user	mpwfuqkdsmwuuk71xoa	Sạc Pin
943	71ccd225	AGV01	go_charge	\N	cancelled	2026-06-02 16:31:54.605255+07	\N	2026-06-02 16:32:01.264476+07	cancelled by user	mpwfuqkdsmwuuk71xoa	Sạc Pin
944	7330c2e0	AGV01	go_to	17	completed	2026-06-02 16:33:36.073285+07	2026-06-02 16:33:36.073285+07	2026-06-02 16:34:13.861696+07	lifecycle:picking:confirmed	mpwfwwxwgwhlznvbobk	A06
947	52753580	AGV02	go_to	16	completed	2026-06-02 16:33:54.7198+07	2026-06-02 16:33:54.7198+07	2026-06-02 16:34:24.045612+07	lifecycle:picking:confirmed	mpwfxbbwptdbtjb8fo	A06
953	a1ea8be4	AGV01	go_to	17	completed	2026-06-02 16:52:15.089544+07	2026-06-02 16:52:44.687846+07	2026-06-02 16:56:21.621005+07	lifecycle:picking:confirmed	mpwgkw9najvwirtvtnp	A06
945	49960697	AGV01	go_to	17	completed	2026-06-02 16:33:36.344235+07	2026-06-02 16:34:13.868361+07	2026-06-02 16:34:54.886778+07	lifecycle:picking:confirmed	mpwfwwxwgwhlznvbobk	A06
969	51017b9f	AGV01	go_to	18	completed	2026-06-03 09:37:15.043998+07	2026-06-03 09:37:15.043998+07	2026-06-03 09:38:05.264324+07	event:continue	4b01f755	Lấy hàng
946	bb477ead	AGV01	go_charge	\N	completed	2026-06-02 16:33:36.361529+07	2026-06-02 16:34:54.887785+07	2026-06-02 16:35:00.356802+07		mpwfwwxwgwhlznvbobk	A06
948	5a9e93ab	AGV02	go_to	16	completed	2026-06-02 16:33:54.749617+07	2026-06-02 16:34:24.045612+07	2026-06-02 16:35:04.491668+07	lifecycle:picking:confirmed	mpwfxbbwptdbtjb8fo	A06
954	02e641a8	AGV01	go_charge	\N	completed	2026-06-02 16:52:15.105382+07	2026-06-02 16:56:21.626883+07	2026-06-02 16:56:27.006452+07		mpwgkw9najvwirtvtnp	A06
975	075928f2	AGV01	go_charge	\N	completed	2026-06-03 10:00:03.26193+07	2026-06-03 10:00:03.26193+07	2026-06-03 10:00:08.412256+07		mpxhanuem9eth1tar4a	Sạc Pin
949	fdfbc145	AGV02	go_charge	\N	completed	2026-06-02 16:33:54.778402+07	2026-06-02 16:35:04.491668+07	2026-06-02 16:35:09.516055+07		mpwfxbbwptdbtjb8fo	A06
950	7e66bfec	AGV01	go_charge	\N	completed	2026-06-02 16:34:54.922328+07	2026-06-02 16:35:00.369043+07	2026-06-02 16:35:41.089479+07	charge_arrived	mpwfwwxwgwhlznvbobk	A06
951	fd4eefa8	AGV02	go_charge	\N	completed	2026-06-02 16:35:04.511467+07	2026-06-02 16:35:09.517062+07	2026-06-02 16:36:13.125776+07	charge_arrived	mpwfxbbwptdbtjb8fo	A06
952	97c26b77	AGV01	go_to	17	completed	2026-06-02 16:52:14.978562+07	2026-06-02 16:52:14.978562+07	2026-06-02 16:52:44.687846+07	lifecycle:picking:confirmed	mpwgkw9najvwirtvtnp	A06
970	a1d736b5	AGV01	go_to	18	completed	2026-06-03 09:37:15.062856+07	2026-06-03 09:38:05.264324+07	2026-06-03 09:38:20.642955+07	event:continue	4b01f755	Lấy hàng
955	12fa7b72	AGV02	go_to	17	running	2026-06-02 16:53:10.313102+07	\N	\N	\N	mpwgm2zngcsd5hn1cb	A06
956	957eafdd	AGV02	go_charge	\N	completed	2026-06-02 16:53:10.33822+07	2026-06-02 16:53:10.33822+07	2026-06-02 16:53:41.002275+07	charge_arrived	mpwgm2zngcsd5hn1cb	A06
957	74d37cb9	AGV02	go_to	17	failed	2026-06-02 16:55:51.058846+07	2026-06-02 16:55:51.058846+07	2026-06-02 16:55:51.060847+07	AGV02: node đích 17 đang bị AGV01 chiếm hoặc heading đến — chờ AGV01 rời khỏi node trước	mpwgpj0ry2q0i49d8q	A06
962	38fe7f19	AGV01	go_charge	\N	cancelled	2026-06-02 16:56:21.716616+07	2026-06-02 16:56:27.00746+07	2026-06-02 17:00:23.638392+07	force-cancelled by user	mpwgkw9najvwirtvtnp	A06
959	244bfd58	AGV02	go_to	15	cancelled	2026-06-02 16:56:07.213694+07	2026-06-02 16:56:07.213694+07	2026-06-02 17:00:32.552019+07	force-cancelled by user	mpwgpvhins9e28hvol	A06
961	2ba045e8	AGV02	go_charge	\N	cancelled	2026-06-02 16:56:07.246478+07	\N	2026-06-02 17:00:32.552019+07	cancelled by user	mpwgpvhins9e28hvol	A06
960	614dfc5a	AGV02	go_to	15	cancelled	2026-06-02 16:56:07.233628+07	\N	2026-06-02 17:00:32.552019+07	cancelled by user	mpwgpvhins9e28hvol	A06
963	25878e48	AGV02	go_charge	\N	completed	2026-06-02 17:00:48.33528+07	2026-06-02 17:00:48.33528+07	2026-06-02 17:00:53.136335+07	lifecycle:picking:confirmed	mpwgvwefnis3neounq	Sạc Pin
964	ef2310bd	AGV02	go_charge	\N	cancelled	2026-06-02 17:00:48.355922+07	2026-06-02 17:00:53.137332+07	2026-06-02 17:01:00.139722+07	force-cancelled by user	mpwgvwefnis3neounq	Sạc Pin
965	2976fa1f	AGV02	go_charge	\N	cancelled	2026-06-02 17:00:53.16052+07	\N	2026-06-02 17:01:00.175373+07	cancelled by user	mpwgvwefnis3neounq	Sạc Pin
966	75fc6a09	AGV01	go_to	\N	failed	2026-06-03 08:50:27.509364+07	2026-06-03 08:50:27.509364+07	2026-06-03 08:50:27.509364+07	dispatch failed	52dcb44c	Lấy hàng
967	f02c082e	AGV01	go_to	\N	failed	2026-06-03 09:15:28.116286+07	2026-06-03 09:15:28.116286+07	2026-06-03 09:15:28.117288+07	dispatch failed	4915c7f3	Lấy hàng
968	1fd0f51e	AGV01	go_to	18	failed	2026-06-03 09:28:04.027872+07	2026-06-03 09:28:04.027872+07	2026-06-03 09:28:14.043488+07	dispatch failed	d651fc1c	Lấy hàng
971	2b8dc46f	AGV01	go_charge	\N	completed	2026-06-03 09:41:08.649597+07	2026-06-03 09:41:08.649597+07	2026-06-03 09:41:13.912877+07		mpxgmcd7e393tvfyi86	Sạc Pin
982	9103971e	AGV02	go_to	18	completed	2026-06-03 10:39:08.073724+07	2026-06-03 10:39:08.073724+07	2026-06-03 10:39:48.392799+07	event:continue	0ddfb1ee	Lấy hàng
972	7b49b766	AGV01	go_charge	\N	completed	2026-06-03 09:41:08.668952+07	2026-06-03 09:41:13.912877+07	2026-06-03 09:41:54.449619+07	charge_arrived	mpxgmcd7e393tvfyi86	Sạc Pin
976	c3a745d9	AGV01	go_charge	\N	completed	2026-06-03 10:00:03.284944+07	2026-06-03 10:00:08.413404+07	2026-06-03 10:00:49.189286+07	charge_arrived	mpxhanuem9eth1tar4a	Sạc Pin
973	5d96a6d9	AGV01	go_to	18	completed	2026-06-03 09:56:15.551825+07	2026-06-03 09:56:15.551825+07	2026-06-03 09:56:50.601613+07	event:continue	f29856ff	Lấy hàng
974	cd2b9c53	AGV01	go_to	18	completed	2026-06-03 09:56:15.62465+07	2026-06-03 09:56:50.602609+07	2026-06-03 09:57:04.713576+07	event:continue	f29856ff	Lấy hàng
977	52a69d7f	AGV01	go_to	18	completed	2026-06-03 10:17:07.383379+07	2026-06-03 10:17:07.383379+07	2026-06-03 10:17:43.706592+07	event:continue	fb88971c	Lấy hàng
978	18771c02	AGV01	go_to	18	cancelled	2026-06-03 10:17:07.447846+07	2026-06-03 10:17:43.706592+07	2026-06-03 10:23:30.155277+07	force-cancelled by user	fb88971c	Lấy hàng
979	08d7bdc6	AGV01	go_charge	\N	cancelled	2026-06-03 10:17:07.448845+07	\N	2026-06-03 10:23:35.623884+07	cancelled by user	fb88971c	Lấy hàng
980	1214d0b4	AGV01	go_charge	\N	completed	2026-06-03 10:23:41.778012+07	2026-06-03 10:23:41.778012+07	2026-06-03 10:23:50.452762+07		mpxi52di5gfgzs4hzzf	Sạc Pin
981	d6fd2333	AGV01	go_charge	\N	completed	2026-06-03 10:23:41.946818+07	2026-06-03 10:23:50.453742+07	2026-06-03 10:24:21.806414+07	charge_arrived	mpxi52di5gfgzs4hzzf	Sạc Pin
984	09df054f	AGV02	go_charge	\N	completed	2026-06-03 10:39:08.238241+07	2026-06-03 10:40:01.854327+07	2026-06-03 10:40:07.025953+07		0ddfb1ee	Lấy hàng
986	6f2f93dd	AGV01	go_to	17	completed	2026-06-03 10:45:24.472256+07	2026-06-03 10:45:24.472256+07	2026-06-03 10:45:54.066872+07	lifecycle:picking:confirmed	mpxiwzjgc17r4fc710g	A06
983	8cc57f7d	AGV02	go_to	18	completed	2026-06-03 10:39:08.236326+07	2026-06-03 10:39:48.393811+07	2026-06-03 10:40:01.853314+07	event:continue	0ddfb1ee	Lấy hàng
985	7d06742e	AGV02	go_charge	\N	completed	2026-06-03 10:40:01.871383+07	2026-06-03 10:40:07.026944+07	2026-06-03 10:40:43.192094+07	charge_arrived	0ddfb1ee	Lấy hàng
988	aacf38eb	AGV01	go_charge	\N	completed	2026-06-03 10:45:24.662414+07	2026-06-03 10:46:18.882126+07	2026-06-03 10:46:26.362341+07		mpxiwzjgc17r4fc710g	A06
990	625d091e	AGV02	go_charge	\N	completed	2026-06-03 10:46:10.874043+07	2026-06-03 10:46:10.874043+07	2026-06-03 10:46:41.63508+07	charge_arrived	mpxixzce4kvh5ibbo1e	A06
1314	69952042	AGV01	go_to	9	cancelled	2026-06-03 16:46:21.148579+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1313	edad835e	AGV01	go_to	19	cancelled	2026-06-03 16:46:14.104008+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1312	1589289d	AGV01	go_to	9	cancelled	2026-06-03 16:46:04.731958+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1311	9db0d2f2	AGV01	go_to	19	cancelled	2026-06-03 16:45:57.753824+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1310	3396d3f5	AGV01	go_to	9	cancelled	2026-06-03 16:45:50.740476+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1309	e6820874	AGV01	go_to	19	cancelled	2026-06-03 16:45:43.744631+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1308	19045ce6	AGV01	go_to	9	cancelled	2026-06-03 16:45:35.579022+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1307	9c2e3766	AGV01	go_to	19	cancelled	2026-06-03 16:45:28.573186+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1306	4d20a0d8	AGV01	go_to	9	cancelled	2026-06-03 16:45:21.537233+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1305	c4db7bd4	AGV01	go_to	19	cancelled	2026-06-03 16:45:14.530261+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1304	9a7a51d5	AGV01	go_to	9	cancelled	2026-06-03 16:45:05.293866+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1303	ecc57f30	AGV01	go_to	19	cancelled	2026-06-03 16:44:58.124699+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1302	3fbd98ea	AGV01	go_to	9	cancelled	2026-06-03 16:44:50.975653+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1301	55ea93fd	AGV01	go_to	19	cancelled	2026-06-03 16:44:43.985333+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1300	a0b71383	AGV01	go_to	9	cancelled	2026-06-03 16:44:36.805106+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1299	1cb7be2f	AGV01	go_to	19	cancelled	2026-06-03 16:44:29.797224+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1298	5f281e8c	AGV01	go_to	9	cancelled	2026-06-03 16:44:22.842935+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1297	636f80b0	AGV01	go_to	19	cancelled	2026-06-03 16:44:15.764211+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1296	02a24947	AGV01	go_to	9	cancelled	2026-06-03 16:44:06.466307+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1295	18b96672	AGV01	go_to	19	cancelled	2026-06-03 16:43:59.277674+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1294	03ef788d	AGV01	go_to	9	cancelled	2026-06-03 16:43:52.223256+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1293	cc4a40ce	AGV01	go_to	19	cancelled	2026-06-03 16:43:45.208726+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1292	2ce98180	AGV01	go_to	9	cancelled	2026-06-03 16:43:35.97742+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1291	ad1dbbe6	AGV01	go_to	19	cancelled	2026-06-03 16:43:28.983947+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1290	d9e35435	AGV01	go_to	9	cancelled	2026-06-03 16:43:21.94492+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1289	16269549	AGV01	go_to	19	cancelled	2026-06-03 16:43:12.399926+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1288	925e43c2	AGV01	go_to	9	cancelled	2026-06-03 16:43:05.402818+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1287	d43d2911	AGV01	go_to	19	cancelled	2026-06-03 16:42:56.171752+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1286	06b1c771	AGV01	go_to	9	cancelled	2026-06-03 16:42:49.180968+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1285	feb8eb88	AGV01	go_to	19	cancelled	2026-06-03 16:42:39.947504+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1284	0fdadac0	AGV01	go_to	9	cancelled	2026-06-03 16:42:32.957598+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1323	d71083a7	AGV01	go_to	19	cancelled	2026-06-03 16:47:41.203721+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1321	275475fa	AGV01	go_to	19	cancelled	2026-06-03 16:47:22.384237+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1322	faec0bd8	AGV01	go_to	9	cancelled	2026-06-03 16:47:31.898775+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1320	634b70e9	AGV01	go_to	9	cancelled	2026-06-03 16:47:15.397465+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1317	7249a783	AGV01	go_to	19	cancelled	2026-06-03 16:46:50.505532+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1316	e40bffc0	AGV01	go_to	9	cancelled	2026-06-03 16:46:37.33105+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1315	fd5d5606	AGV01	go_to	19	cancelled	2026-06-03 16:46:30.384095+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1318	d111f8af	AGV01	go_to	9	cancelled	2026-06-03 16:46:57.485328+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1319	24f989bb	AGV01	go_to	19	cancelled	2026-06-03 16:47:08.400169+07	\N	2026-06-03 16:47:46.435836+07	cancelled by user	mpxvlt1eo8wkq5ur75	A06
1378	b7add310	AGV02	go_charge	\N	completed	2026-06-04 08:55:08.657382+07	2026-06-04 08:55:08.657382+07	2026-06-04 08:55:14.289612+07		mpyuf1f2esznbmckk5g	Sạc Pin
1510	66c911ef	AGV01	go_to	64	cancelled	2026-06-04 15:48:36.21112+07	\N	2026-06-04 15:53:56.330767+07	cancelled by user	mpz969q852xh5uw5sx	A02
1508	feba887a	AGV01	go_to	96	cancelled	2026-06-04 15:48:13.851512+07	\N	2026-06-04 15:53:56.330767+07	cancelled by user	mpz969q852xh5uw5sx	A02
1454	40a183b1	AGV02	go_to	17	completed	2026-06-04 10:24:31.691955+07	2026-06-04 10:24:58.560636+07	2026-06-04 10:25:19.720599+07	lifecycle:picking:confirmed	mpyxlzeekupi70eumyf	A06
1456	e7af7bcf	AGV01	go_to	17	completed	2026-06-04 10:24:42.939531+07	2026-06-04 10:24:42.939531+07	2026-06-04 10:25:23.877155+07	lifecycle:picking:confirmed	mpyxm88lr60uxwl8rk	A06
1455	7e5ba4fb	AGV02	go_charge	\N	completed	2026-06-04 10:24:31.707525+07	2026-06-04 10:25:19.720599+07	2026-06-04 10:25:28.672236+07		mpyxlzeekupi70eumyf	A06
1507	2099c30a	AGV01	go_to	18	cancelled	2026-06-04 15:48:13.833514+07	\N	2026-06-04 15:53:56.330767+07	cancelled by user	mpz969q852xh5uw5sx	A02
1509	1b280779	AGV01	go_charge	\N	cancelled	2026-06-04 15:48:13.857552+07	\N	2026-06-04 15:53:56.330767+07	cancelled by user	mpz969q852xh5uw5sx	A02
1658	280de3b5	AGV01	go_to	17	completed	2026-06-05 09:55:51.23215+07	2026-06-05 09:55:51.23215+07	2026-06-05 09:56:27.644231+07	lifecycle:picking:confirmed	mq0c0ypbw4ol00oy2h	A06
1566	585ac3c8	AGV02	go_charge	\N	completed	2026-06-05 09:03:31.230294+07	2026-06-05 09:03:42.456685+07	2026-06-05 09:03:42.475223+07	bounce_wait	mq0a4k1iw4upmka8qq	A06
1568	631bf901	AGV02	go_to	13	completed	2026-06-05 09:04:03.37733+07	2026-06-05 09:04:11.864753+07	2026-06-05 09:04:22.20226+07		\N	bounce_retry
1661	f9c31325	AGV02	go_to	17	completed	2026-06-05 09:56:09.287483+07	2026-06-05 09:56:09.287483+07	2026-06-05 09:56:40.157029+07	lifecycle:picking:confirmed	mq0c1cn5xh357t2eg5	A06
1659	f30c201b	AGV01	go_to	17	completed	2026-06-05 09:55:51.313863+07	2026-06-05 09:56:27.654236+07	2026-06-05 09:56:49.576669+07	lifecycle:picking:confirmed	mq0c0ypbw4ol00oy2h	A06
1660	c65ee5b2	AGV01	go_charge	\N	completed	2026-06-05 09:55:51.340867+07	2026-06-05 09:56:49.577673+07	2026-06-05 09:57:08.093155+07		mq0c0ypbw4ol00oy2h	A06
989	e4b801d5	AGV02	go_to	17	running	2026-06-03 10:46:10.865029+07	\N	\N	\N	mpxixzce4kvh5ibbo1e	A06
987	e50734c4	AGV01	go_to	17	completed	2026-06-03 10:45:24.643078+07	2026-06-03 10:45:54.067872+07	2026-06-03 10:46:18.874346+07	lifecycle:picking:confirmed	mpxiwzjgc17r4fc710g	A06
1010	d81e2268	AGV01	go_to	17	completed	2026-06-03 11:44:03.551491+07	2026-06-03 11:44:33.331584+07	2026-06-03 11:46:15.159032+07	lifecycle:picking:confirmed	mpxl0ev1n0ezoosbz7	A06
991	aacb02ae	AGV01	go_charge	\N	completed	2026-06-03 10:46:19.079725+07	2026-06-03 10:46:26.362341+07	2026-06-03 10:47:12.400036+07	charge_arrived	mpxiwzjgc17r4fc710g	A06
992	830cb709	AGV01	go_to	17	completed	2026-06-03 10:52:32.631173+07	2026-06-03 10:52:32.631173+07	2026-06-03 10:52:59.848198+07	lifecycle:picking:confirmed	mpxj65wu0jhzcwxy870a	A06
1026	9556182e	AGV02	go_to	17	cancelled	2026-06-03 13:30:23.542124+07	\N	2026-06-03 13:30:27.639693+07	cancelled by user	mpxoek32srjwokoiyx	A06
993	abf9f064	AGV01	go_to	17	completed	2026-06-03 10:52:32.849265+07	2026-06-03 10:52:59.848198+07	2026-06-03 10:53:40.128554+07	lifecycle:picking:confirmed	mpxj65wu0jhzcwxy870a	A06
1015	3eef3781	AGV02	go_to	17	completed	2026-06-03 11:45:35.565232+07	2026-06-03 11:45:35.565232+07	2026-06-03 11:46:26.034723+07		mpxl2dvtimlc42mow3g	A06
994	154bbb53	AGV01	go_charge	\N	completed	2026-06-03 10:52:32.869269+07	2026-06-03 10:53:40.128554+07	2026-06-03 10:53:45.454449+07		mpxj65wu0jhzcwxy870a	A06
1024	0d45cfed	AGV02	go_charge	\N	cancelled	2026-06-03 13:19:02.374655+07	\N	2026-06-03 13:30:27.639693+07	cancelled by user	mpxoek32srjwokoiyx	A06
995	cc23345c	AGV02	go_to	17	cancelled	2026-06-03 10:53:15.075342+07	2026-06-03 10:53:15.075342+07	2026-06-03 11:03:14.212082+07	force-cancelled by user	mpxj72nz8ywm4ehpz1q	A06
996	f03e9a56	AGV02	go_to	17	cancelled	2026-06-03 10:53:15.112868+07	\N	2026-06-03 11:03:14.212082+07	cancelled by user	mpxj72nz8ywm4ehpz1q	A06
997	5775e95f	AGV02	go_charge	\N	cancelled	2026-06-03 10:53:15.13091+07	\N	2026-06-03 11:03:14.212082+07	cancelled by user	mpxj72nz8ywm4ehpz1q	A06
1000	d1cd7d84	AGV02	go_charge	\N	cancelled	2026-06-03 11:03:21.332403+07	\N	2026-06-03 11:03:29.865136+07	cancelled by user	mpxjk2c5ucx4j3k523b	Sạc Pin
999	9744646d	AGV02	go_charge	\N	cancelled	2026-06-03 11:03:21.190736+07	2026-06-03 11:03:21.190736+07	2026-06-03 11:03:29.865136+07	force-cancelled by user	mpxjk2c5ucx4j3k523b	Sạc Pin
1001	895cfbf0	AGV02	go_charge	\N	cancelled	2026-06-03 11:04:16.356131+07	2026-06-03 11:04:16.356131+07	2026-06-03 11:04:25.754675+07	force-cancelled by user	mpxjl8wp4rh7k28bpa6	Sạc Pin
998	a87d0e59	AGV01	go_charge	\N	completed	2026-06-03 10:53:40.14355+07	2026-06-03 10:53:45.455449+07	2026-06-03 11:05:16.417781+07	charge_arrived	mpxj65wu0jhzcwxy870a	A06
1016	fe3d1e21	AGV02	go_to	17	completed	2026-06-03 11:45:35.580253+07	2026-06-03 11:46:26.034723+07	2026-06-03 11:47:11.330333+07	lifecycle:picking:confirmed	mpxl2dvtimlc42mow3g	A06
1002	29ba4526	AGV01	go_to	17	completed	2026-06-03 11:09:57.848639+07	2026-06-03 11:09:57.848639+07	2026-06-03 11:10:32.122392+07	lifecycle:picking:confirmed	mpxjskeojx6408qixw	A06
1023	3effb06b	AGV02	go_to	17	cancelled	2026-06-03 13:19:02.361466+07	2026-06-03 13:30:23.157819+07	2026-06-03 13:30:27.635692+07	force-cancelled by user	mpxoek32srjwokoiyx	A06
1003	562b75f9	AGV01	go_to	17	completed	2026-06-03 11:09:57.904515+07	2026-06-03 11:10:32.122392+07	2026-06-03 11:11:14.207569+07	lifecycle:picking:confirmed	mpxjskeojx6408qixw	A06
1005	57f82c47	AGV02	go_to	17	cancelled	2026-06-03 11:10:48.150919+07	2026-06-03 11:10:48.150919+07	2026-06-03 11:13:46.289948+07	force-cancelled by user	mpxjtn853jfapx3l9gf	A06
1006	c730876d	AGV02	go_to	17	cancelled	2026-06-03 11:10:48.165437+07	\N	2026-06-03 11:13:46.290946+07	cancelled by user	mpxjtn853jfapx3l9gf	A06
1007	ef8273e4	AGV02	go_charge	\N	cancelled	2026-06-03 11:10:48.176454+07	\N	2026-06-03 11:13:46.290946+07	cancelled by user	mpxjtn853jfapx3l9gf	A06
1004	abfd7ea0	AGV01	go_charge	\N	completed	2026-06-03 11:09:57.916886+07	2026-06-03 11:11:14.207569+07	2026-06-03 11:14:02.208968+07		mpxjskeojx6408qixw	A06
1008	3e4e8b72	AGV01	go_charge	\N	completed	2026-06-03 11:11:14.227571+07	2026-06-03 11:14:02.210067+07	2026-06-03 11:14:46.901326+07	charge_arrived	mpxjskeojx6408qixw	A06
1009	4c619b01	AGV01	go_to	17	completed	2026-06-03 11:44:03.529467+07	2026-06-03 11:44:03.529467+07	2026-06-03 11:44:33.330583+07	lifecycle:picking:confirmed	mpxl0ev1n0ezoosbz7	A06
1025	77cf5293	AGV01	go_charge	\N	completed	2026-06-03 13:19:20.744618+07	2026-06-03 13:19:26.119534+07	2026-06-03 13:31:18.667487+07	charge_arrived	mpxodr7u9tjzpxaorwq	A06
1012	60915993	AGV02	go_to	17	cancelled	2026-06-03 11:44:38.833052+07	2026-06-03 11:44:38.833052+07	2026-06-03 11:44:57.483691+07	force-cancelled by user	mpxl163xpmm3cuaqfv	A06
1014	f80d06c2	AGV02	go_charge	\N	cancelled	2026-06-03 11:44:38.865053+07	\N	2026-06-03 11:44:57.483691+07	cancelled by user	mpxl163xpmm3cuaqfv	A06
1013	cd0ed32b	AGV02	go_to	17	cancelled	2026-06-03 11:44:38.84805+07	\N	2026-06-03 11:44:57.483691+07	cancelled by user	mpxl163xpmm3cuaqfv	A06
1017	5975f248	AGV02	go_charge	\N	completed	2026-06-03 11:45:35.595233+07	2026-06-03 11:47:11.331329+07	2026-06-03 11:47:17.072882+07		mpxl2dvtimlc42mow3g	A06
1018	1472374f	AGV02	go_charge	\N	completed	2026-06-03 11:47:11.386864+07	2026-06-03 11:47:17.080889+07	2026-06-03 11:47:55.60197+07	charge_arrived	mpxl2dvtimlc42mow3g	A06
1011	9f816843	AGV01	go_charge	\N	completed	2026-06-03 11:44:03.566006+07	2026-06-03 11:46:15.160161+07	2026-06-03 11:48:01.655759+07	charge_arrived	mpxl0ev1n0ezoosbz7	A06
1019	52e96e69	AGV01	go_to	17	completed	2026-06-03 13:18:24.967189+07	2026-06-03 13:18:24.967189+07	2026-06-03 13:18:55.539439+07	lifecycle:picking:confirmed	mpxodr7u9tjzpxaorwq	A06
1027	bcbbe677	AGV01	go_to	17	failed	2026-06-03 13:33:55.382792+07	2026-06-03 13:33:55.382792+07	2026-06-03 13:33:55.415799+07	'TrafficCoordinator' object has no attribute 'state_store'	mpxoxp5u14yqps3nlvji	A06
1020	6d92a844	AGV01	go_to	17	completed	2026-06-03 13:18:25.553454+07	2026-06-03 13:18:55.539439+07	2026-06-03 13:19:20.71209+07	lifecycle:picking:confirmed	mpxodr7u9tjzpxaorwq	A06
1021	46f28321	AGV01	go_charge	\N	completed	2026-06-03 13:18:25.578446+07	2026-06-03 13:19:20.71209+07	2026-06-03 13:19:26.113569+07		mpxodr7u9tjzpxaorwq	A06
1031	516fc4ea	AGV01	go_to	17	completed	2026-06-03 13:36:38.814761+07	2026-06-03 13:36:38.814761+07	2026-06-03 13:37:20.854106+07	lifecycle:picking:confirmed	mpxp17a1emlb9o3kjz7	A06
1022	00172dd3	AGV02	go_to	17	completed	2026-06-03 13:19:02.324336+07	2026-06-03 13:19:02.324336+07	2026-06-03 13:30:23.156771+07	lifecycle:picking:confirmed	mpxoek32srjwokoiyx	A06
1033	4ba68836	AGV01	go_charge	\N	completed	2026-06-03 13:36:38.996813+07	2026-06-03 13:37:48.40334+07	2026-06-03 13:37:53.65358+07		mpxp17a1emlb9o3kjz7	A06
1028	27385a54	AGV01	go_charge	\N	completed	2026-06-03 13:33:55.433751+07	2026-06-03 13:33:55.433751+07	2026-06-03 13:33:57.33355+07	charge_arrived	mpxoxp5u14yqps3nlvji	A06
1029	56be63e6	AGV01	go_to	17	failed	2026-06-03 13:34:17.966992+07	2026-06-03 13:34:17.966992+07	2026-06-03 13:34:17.989975+07	'TrafficCoordinator' object has no attribute 'state_store'	mpxoy6lm0lhh7mtqwza	A06
1030	548190d9	AGV01	go_charge	\N	completed	2026-06-03 13:34:18.003975+07	2026-06-03 13:34:18.003975+07	2026-06-03 13:34:19.673164+07	charge_arrived	mpxoy6lm0lhh7mtqwza	A06
1032	9306063f	AGV01	go_to	17	completed	2026-06-03 13:36:38.982757+07	2026-06-03 13:37:20.854106+07	2026-06-03 13:37:48.40233+07	lifecycle:picking:confirmed	mpxp17a1emlb9o3kjz7	A06
1034	38169963	AGV02	go_to	17	completed	2026-06-03 13:37:28.160914+07	2026-06-03 13:37:28.160914+07	2026-06-03 13:43:24.523936+07	lifecycle:picking:confirmed	mpxp29crp2qvc0bf638	A06
1039	cb44fab3	AGV01	go_to	9	cancelled	2026-06-03 13:38:22.30527+07	\N	2026-06-03 13:44:19.283433+07	cancelled by user	mpxp17a1emlb9o3kjz7	A06
2791	f7592c2f	AGV01	go_charge	\N	completed	2026-06-15 10:56:13.288566+07	2026-06-15 10:56:13.288561+07	2026-06-15 10:56:27.718068+07	off_route	mqeoijy2p8n8127dea	yield_resume
1325	1631b045	AGV02	go_charge	\N	completed	2026-06-03 16:47:57.954276+07	2026-06-03 16:48:06.685606+07	2026-06-03 16:48:35.126976+07	charge_arrived	mpxvv8mgspjjcvwxu8q	Sạc Pin
1037	845e5d5d	AGV01	go_charge	\N	cancelled	2026-06-03 13:37:48.426337+07	2026-06-03 13:37:53.65358+07	2026-06-03 13:44:19.283433+07	force-cancelled by user	mpxp17a1emlb9o3kjz7	A06
1035	3b41a6d3	AGV02	go_to	17	failed	2026-06-03 13:37:28.202316+07	2026-06-03 13:43:24.523936+07	2026-06-03 13:43:24.793492+07	'TrafficCoordinator' object has no attribute '_is_same_direction'	mpxp29crp2qvc0bf638	A06
1038	b6d5ed89	AGV01	go_to	13	cancelled	2026-06-03 13:38:15.327658+07	\N	2026-06-03 13:44:19.283433+07	cancelled by user	mpxp17a1emlb9o3kjz7	A06
1041	3ab65d02	AGV01	go_to	9	cancelled	2026-06-03 13:38:38.679969+07	\N	2026-06-03 13:44:19.283433+07	cancelled by user	mpxp17a1emlb9o3kjz7	A06
1044	6520c329	AGV01	go_to	18	cancelled	2026-06-03 13:38:59.818464+07	\N	2026-06-03 13:44:19.283433+07	cancelled by user	mpxp17a1emlb9o3kjz7	A06
1043	9b41e820	AGV01	go_to	9	cancelled	2026-06-03 13:38:52.823466+07	\N	2026-06-03 13:44:19.283433+07	cancelled by user	mpxp17a1emlb9o3kjz7	A06
1036	c9f5d405	AGV02	go_charge	\N	cancelled	2026-06-03 13:37:28.232863+07	\N	2026-06-03 13:43:33.416486+07	cancelled by user	mpxp29crp2qvc0bf638	A06
1048	be9c6734	AGV01	go_to	18	cancelled	2026-06-03 13:39:30.092516+07	\N	2026-06-03 13:44:19.283433+07	cancelled by user	mpxp17a1emlb9o3kjz7	A06
1047	10a2b928	AGV01	go_to	9	cancelled	2026-06-03 13:39:23.094237+07	\N	2026-06-03 13:44:19.283433+07	cancelled by user	mpxp17a1emlb9o3kjz7	A06
1046	fcfc56bd	AGV01	go_to	18	cancelled	2026-06-03 13:39:16.059551+07	\N	2026-06-03 13:44:19.283433+07	cancelled by user	mpxp17a1emlb9o3kjz7	A06
1045	6621b914	AGV01	go_to	9	cancelled	2026-06-03 13:39:09.104919+07	\N	2026-06-03 13:44:19.283433+07	cancelled by user	mpxp17a1emlb9o3kjz7	A06
1042	3eb68e38	AGV01	go_to	18	cancelled	2026-06-03 13:38:45.685613+07	\N	2026-06-03 13:44:19.283433+07	cancelled by user	mpxp17a1emlb9o3kjz7	A06
1040	21405689	AGV01	go_to	18	cancelled	2026-06-03 13:38:29.321743+07	\N	2026-06-03 13:44:19.283433+07	cancelled by user	mpxp17a1emlb9o3kjz7	A06
1049	b3f37a3e	AGV01	go_charge	\N	completed	2026-06-03 13:44:27.16875+07	2026-06-03 13:44:27.16875+07	2026-06-03 13:44:32.310294+07		mpxpb8nj3sboyw6i897	Sạc Pin
1068	e652e7b6	AGV01	go_charge	\N	completed	2026-06-03 14:01:32.271916+07	2026-06-03 14:01:37.479202+07	2026-06-03 14:09:06.79273+07	charge_arrived	mpxpvp3wujfiuwp348	A06
1050	e266e773	AGV01	go_charge	\N	completed	2026-06-03 13:44:27.245862+07	2026-06-03 13:44:32.311417+07	2026-06-03 13:45:09.123739+07	charge_arrived	mpxpb8nj3sboyw6i897	Sạc Pin
1051	e461f58e	AGV01	go_to	17	completed	2026-06-03 13:47:36.855977+07	2026-06-03 13:47:36.855977+07	2026-06-03 13:48:26.945103+07	lifecycle:picking:confirmed	mpxpfb0s6cgwv7y6d72	A06
1069	d50422b6	AGV01	go_to	17	running	2026-06-03 14:23:41.336292+07	\N	\N	\N	mpxqpp56eriyqvksqel	A06
1052	ac4cb134	AGV01	go_to	17	completed	2026-06-03 13:47:37.226513+07	2026-06-03 13:48:26.945103+07	2026-06-03 13:48:58.031122+07	lifecycle:picking:confirmed	mpxpfb0s6cgwv7y6d72	A06
1070	312e8b76	AGV01	go_to	17	queued	2026-06-03 14:23:41.384865+07	\N	\N	\N	mpxqpp56eriyqvksqel	A06
1053	ada3f602	AGV01	go_charge	\N	completed	2026-06-03 13:47:37.249051+07	2026-06-03 13:48:58.031122+07	2026-06-03 13:49:03.256357+07		mpxpfb0s6cgwv7y6d72	A06
1071	dadadb05	AGV01	go_charge	\N	queued	2026-06-03 14:23:41.403846+07	\N	\N	\N	mpxqpp56eriyqvksqel	A06
1054	835a7eea	AGV02	go_to	17	completed	2026-06-03 13:48:42.666499+07	2026-06-03 13:48:42.666499+07	2026-06-03 13:49:12.059058+07	lifecycle:picking:confirmed	mpxpgpszhqby5h6aq8	A06
1055	1aee1d05	AGV02	go_to	17	failed	2026-06-03 13:48:42.712505+07	2026-06-03 13:49:12.060052+07	2026-06-03 13:49:12.093056+07	local variable '_line_dir' referenced before assignment	mpxpgpszhqby5h6aq8	A06
1072	d084d101	AGV02	go_to	17	failed	2026-06-03 14:26:04.681238+07	2026-06-03 14:26:04.681238+07	2026-06-03 14:26:04.702247+07	'TrafficCoordinator' object has no attribute '_is_same_direction'	mpxqsrr0uyjvryruoa	A06
1058	713f1f98	AGV02	go_charge	\N	completed	2026-06-03 13:57:06.133078+07	2026-06-03 13:57:06.133078+07	2026-06-03 13:57:16.78427+07		mpxpri9qbrkxk8v8r3k	Sạc Pin
1059	4ca6bbd9	AGV02	go_charge	\N	completed	2026-06-03 13:57:06.319047+07	2026-06-03 13:57:16.785779+07	2026-06-03 13:57:40.80222+07	charge_arrived	mpxpri9qbrkxk8v8r3k	Sạc Pin
1056	ba7340ec	AGV02	go_charge	\N	completed	2026-06-03 13:48:42.735021+07	2026-06-03 13:57:40.803217+07	2026-06-03 13:57:44.473061+07	charge_arrived	mpxpgpszhqby5h6aq8	A06
1057	76053d3b	AGV01	go_charge	\N	cancelled	2026-06-03 13:48:58.057352+07	2026-06-03 13:49:03.258383+07	2026-06-03 13:57:58.954897+07	force-cancelled by user	mpxpfb0s6cgwv7y6d72	A06
1060	1c91a1b3	AGV01	go_charge	\N	cancelled	2026-06-03 13:58:06.805171+07	2026-06-03 13:58:06.805171+07	2026-06-03 13:58:19.033832+07	force-cancelled by user	mpxpst3hf0koaczrc98	Sạc Pin
1061	acd2a2a5	AGV01	go_to	17	completed	2026-06-03 14:00:21.609534+07	2026-06-03 14:00:21.609534+07	2026-06-03 14:00:59.50435+07	lifecycle:picking:confirmed	mpxpvp3wujfiuwp348	A06
1073	e73301f1	AGV02	go_charge	\N	completed	2026-06-03 14:26:04.722768+07	2026-06-03 14:26:04.722768+07	2026-06-03 14:26:07.144212+07	charge_arrived	mpxqsrr0uyjvryruoa	A06
1062	1c3065fa	AGV01	go_to	17	completed	2026-06-03 14:00:21.733106+07	2026-06-03 14:00:59.50435+07	2026-06-03 14:01:32.251913+07	lifecycle:picking:confirmed	mpxpvp3wujfiuwp348	A06
1063	7cc81cd0	AGV01	go_charge	\N	completed	2026-06-03 14:00:21.745113+07	2026-06-03 14:01:32.252911+07	2026-06-03 14:01:37.477203+07		mpxpvp3wujfiuwp348	A06
1080	9ee566ae	AGV02	go_to	17	completed	2026-06-03 14:32:19.06435+07	2026-06-03 14:32:19.06435+07	2026-06-03 14:33:01.727446+07	lifecycle:picking:confirmed	mpxr0smrq4npe0nz4t	A06
1064	9819df33	AGV02	go_to	17	cancelled	2026-06-03 14:00:37.131963+07	2026-06-03 14:00:37.131963+07	2026-06-03 14:08:00.520052+07	force-cancelled by user	mpxpw138i9ow7u6tyc	A06
1066	015f2472	AGV02	go_charge	\N	cancelled	2026-06-03 14:00:37.169955+07	\N	2026-06-03 14:08:00.521053+07	cancelled by user	mpxpw138i9ow7u6tyc	A06
1067	34338014	AGV02	go_to	19	cancelled	2026-06-03 14:01:05.875551+07	\N	2026-06-03 14:08:00.521053+07	cancelled by user	mpxpw138i9ow7u6tyc	A06
1065	8eaeddf9	AGV02	go_to	17	cancelled	2026-06-03 14:00:37.150966+07	\N	2026-06-03 14:08:00.521053+07	cancelled by user	mpxpw138i9ow7u6tyc	A06
1074	79eea08b	AGV01	go_charge	\N	cancelled	2026-06-03 14:30:16.139443+07	2026-06-03 14:30:16.139443+07	2026-06-03 14:30:28.680186+07	force-cancelled by user	mpxqy5s6msz9nupswnr	Sạc Pin
1087	2bea03f9	AGV01	go_to	17	completed	2026-06-03 14:49:12.750699+07	2026-06-03 14:49:12.750699+07	2026-06-03 14:49:45.880716+07	lifecycle:picking:confirmed	mpxrmisph4amztq2gj4	A06
1075	7f26bd56	AGV01	go_charge	\N	completed	2026-06-03 14:30:39.707222+07	2026-06-03 14:30:39.707222+07	2026-06-03 14:30:48.138391+07		mpxqynyt42gngdf4s27	Sạc Pin
1076	e9dca1cb	AGV01	go_charge	\N	completed	2026-06-03 14:30:39.727765+07	2026-06-03 14:30:48.13939+07	2026-06-03 14:31:18.555164+07	charge_arrived	mpxqynyt42gngdf4s27	Sạc Pin
1077	0b722948	AGV01	go_to	17	completed	2026-06-03 14:32:00.068044+07	2026-06-03 14:32:00.068044+07	2026-06-03 14:32:35.997983+07	lifecycle:picking:confirmed	mpxr0dz3uuujbza4fyp	A06
1078	0b23afdd	AGV01	go_to	17	completed	2026-06-03 14:32:00.174664+07	2026-06-03 14:32:35.997983+07	2026-06-03 14:32:54.9755+07	lifecycle:picking:confirmed	mpxr0dz3uuujbza4fyp	A06
1079	f89c140c	AGV01	go_charge	\N	completed	2026-06-03 14:32:00.188657+07	2026-06-03 14:32:54.983496+07	2026-06-03 14:33:00.371086+07		mpxr0dz3uuujbza4fyp	A06
1091	d3c1f13f	AGV02	go_to	17	completed	2026-06-03 14:49:35.739131+07	2026-06-03 14:50:06.356276+07	2026-06-03 14:50:52.957735+07	lifecycle:picking:confirmed	mpxrn0irk6rri1n3m	A06
1081	01fb845c	AGV02	go_to	17	cancelled	2026-06-03 14:32:19.090349+07	2026-06-03 14:33:01.727446+07	2026-06-03 14:34:35.174747+07	force-cancelled by user	mpxr0smrq4npe0nz4t	A06
1082	4daa8418	AGV02	go_charge	\N	cancelled	2026-06-03 14:32:19.106363+07	\N	2026-06-03 14:34:35.195271+07	cancelled by user	mpxr0smrq4npe0nz4t	A06
1083	9cb4e791	AGV01	go_charge	\N	cancelled	2026-06-03 14:32:55.022005+07	2026-06-03 14:33:00.377096+07	2026-06-03 14:34:39.977918+07	force-cancelled by user	mpxr0dz3uuujbza4fyp	A06
1085	456dba99	AGV01	go_to	10	cancelled	2026-06-03 14:33:28.398897+07	\N	2026-06-03 14:34:39.978917+07	cancelled by user	mpxr0dz3uuujbza4fyp	A06
1084	62272a99	AGV01	go_to	13	cancelled	2026-06-03 14:33:21.363885+07	\N	2026-06-03 14:34:39.978917+07	cancelled by user	mpxr0dz3uuujbza4fyp	A06
1086	f4208c36	AGV02	go_charge	\N	cancelled	2026-06-03 14:46:49.671637+07	2026-06-03 14:46:49.671637+07	2026-06-03 14:46:59.026664+07	force-cancelled by user	mpxrjgdoqq4pmtgk59k	Sạc Pin
1094	4b260a87	AGV02	go_to	5	failed	2026-06-03 14:50:24.515409+07	2026-06-03 14:50:52.958739+07	2026-06-03 14:50:52.964792+07	AGV02: đã ở tại 5	mpxrn0irk6rri1n3m	A06
1090	8f267663	AGV02	go_to	17	completed	2026-06-03 14:49:35.721116+07	2026-06-03 14:49:35.721116+07	2026-06-03 14:50:06.356276+07	lifecycle:picking:confirmed	mpxrn0irk6rri1n3m	A06
1088	d9bfb08b	AGV01	go_to	17	completed	2026-06-03 14:49:12.779699+07	2026-06-03 14:49:45.880716+07	2026-06-03 14:50:23.081466+07	lifecycle:picking:confirmed	mpxrmisph4amztq2gj4	A06
1092	0f3b94e0	AGV02	go_charge	\N	cancelled	2026-06-03 14:49:35.75364+07	\N	2026-06-03 14:52:21.664956+07	cancelled by user	mpxrn0irk6rri1n3m	A06
1089	ebc664bb	AGV01	go_charge	\N	completed	2026-06-03 14:49:12.798707+07	2026-06-03 14:50:23.081466+07	2026-06-03 14:51:53.427773+07	charge_arrived	mpxrmisph4amztq2gj4	A06
1093	7eb56a45	AGV02	go_to	17	cancelled	2026-06-03 14:50:06.38827+07	\N	2026-06-03 14:52:21.664956+07	cancelled by user	mpxrn0irk6rri1n3m	A06
1095	2caf70cb	AGV02	go_charge	\N	completed	2026-06-03 14:52:25.895501+07	2026-06-03 14:52:25.895501+07	2026-06-03 14:52:30.968815+07		mpxrqntwft90m7270kf	Sạc Pin
1098	db5ac439	AGV01	go_to	17	completed	2026-06-03 15:10:26.153164+07	2026-06-03 15:10:58.250581+07	2026-06-03 15:11:28.087145+07	lifecycle:picking:confirmed	mpxsdtc5adgk9969sc8	A06
1096	40708cdd	AGV02	go_charge	\N	completed	2026-06-03 14:52:25.907502+07	2026-06-03 14:52:30.968815+07	2026-06-03 14:53:13.548655+07	charge_arrived	mpxrqntwft90m7270kf	Sạc Pin
1102	5e631336	AGV02	go_charge	\N	queued	2026-06-03 15:10:52.880773+07	\N	\N	\N	mpxsedyeya1skksgoa	A06
1097	74a922c7	AGV01	go_to	17	completed	2026-06-03 15:10:26.125154+07	2026-06-03 15:10:26.125154+07	2026-06-03 15:10:58.249581+07	lifecycle:picking:confirmed	mpxsdtc5adgk9969sc8	A06
1101	39c586e1	AGV02	go_to	17	running	2026-06-03 15:10:52.862766+07	2026-06-03 15:11:22.284908+07	\N		mpxsedyeya1skksgoa	A06
1100	779094db	AGV02	go_to	17	completed	2026-06-03 15:10:52.842781+07	2026-06-03 15:10:52.842781+07	2026-06-03 15:11:22.278868+07	lifecycle:picking:confirmed	mpxsedyeya1skksgoa	A06
1099	1420f621	AGV01	go_charge	\N	running	2026-06-03 15:10:26.163682+07	2026-06-03 15:11:28.088151+07	\N		mpxsdtc5adgk9969sc8	A06
1104	4a0756e0	AGV01	go_charge	\N	queued	2026-06-03 15:11:28.108148+07	\N	\N	\N	mpxsdtc5adgk9969sc8	A06
1105	00b37811	AGV01	go_to	5	queued	2026-06-03 15:11:39.373813+07	\N	\N	\N	mpxsdtc5adgk9969sc8	A06
1106	4a14519e	AGV01	go_to	6	queued	2026-06-03 15:11:46.363527+07	\N	\N	\N	mpxsdtc5adgk9969sc8	A06
1107	17e8bd27	AGV02	go_to	5	queued	2026-06-03 15:11:46.860213+07	\N	\N	\N	mpxsedyeya1skksgoa	A06
1108	4e158fe0	AGV01	go_to	7	queued	2026-06-03 15:11:57.28988+07	\N	\N	\N	mpxsdtc5adgk9969sc8	A06
1109	670e9e7d	AGV02	go_to	10	queued	2026-06-03 15:12:02.390256+07	\N	\N	\N	mpxsedyeya1skksgoa	A06
1110	b49a7d97	AGV01	go_to	6	queued	2026-06-03 15:12:04.288237+07	\N	\N	\N	mpxsdtc5adgk9969sc8	A06
1324	034728e7	AGV02	go_charge	\N	completed	2026-06-03 16:47:57.93346+07	2026-06-03 16:47:57.93346+07	2026-06-03 16:48:06.685606+07		mpxvv8mgspjjcvwxu8q	Sạc Pin
1380	5961f3c6	AGV01	go_charge	\N	completed	2026-06-04 08:55:33.108451+07	2026-06-04 08:55:33.108451+07	2026-06-04 08:55:39.323456+07		mpyufka3fx24g2t2nv	Sạc Pin
1735	004f1e37	AGV01	go_charge	\N	cancelled	2026-06-05 10:33:03.825353+07	\N	2026-06-05 10:41:44.242042+07	cancelled by user	mq0dbhd5qboylpqny8	A06
1381	6321eab7	AGV01	go_charge	\N	completed	2026-06-04 08:55:33.133965+07	2026-06-04 08:55:39.324454+07	2026-06-04 08:56:23.754634+07	charge_arrived	mpyufka3fx24g2t2nv	Sạc Pin
1459	902acaa8	AGV02	go_charge	\N	running	2026-06-04 10:25:19.759163+07	2026-06-04 10:25:28.674237+07	\N		mpyxlzeekupi70eumyf	A06
1460	3025d466	AGV02	go_charge	\N	queued	2026-06-04 10:25:28.691237+07	\N	\N	\N	mpyxlzeekupi70eumyf	A06
1461	2121db41	AGV01	go_to	17	queued	2026-06-04 10:25:38.14669+07	\N	\N	\N	mpyxm88lr60uxwl8rk	A06
1462	4f4db9be	AGV02	go_to	5	queued	2026-06-04 10:25:38.663174+07	\N	\N	\N	mpyxlzeekupi70eumyf	A06
1511	de003a81	AGV01	go_charge	\N	completed	2026-06-04 15:54:03.002288+07	2026-06-04 15:54:03.002288+07	2026-06-04 15:54:08.383146+07		mpz9dr7876snp8u8z8r	Sạc Pin
1573	91f74425	AGV02	go_to	17	completed	2026-06-05 09:13:10.34882+07	2026-06-05 09:13:10.34882+07	2026-06-05 09:13:43.179479+07	lifecycle:picking:confirmed	mq0ai2psanec35p5cqk	A06
1579	7545a3b2	AGV01	go_to	19	cancelled	2026-06-05 09:13:36.848658+07	\N	2026-06-05 09:14:42.724707+07	cancelled by user	mq0aighzosjik0o4cxh	A06
1577	f1c45d28	AGV01	go_to	17	cancelled	2026-06-05 09:13:28.236054+07	\N	2026-06-05 09:14:42.724707+07	cancelled by user	mq0aighzosjik0o4cxh	A06
1578	671260ba	AGV01	go_charge	\N	cancelled	2026-06-05 09:13:28.246575+07	\N	2026-06-05 09:14:42.724707+07	cancelled by user	mq0aighzosjik0o4cxh	A06
1585	6a8ca635	AGV01	go_to	69	cancelled	2026-06-05 09:15:47.387951+07	2026-06-05 09:15:56.873034+07	2026-06-05 09:17:23.791087+07	force-cancelled by user	mq0akydcwef4z9vo7to	A06
1591	04df6db0	AGV02	go_to	17	completed	2026-06-05 09:18:58.943136+07	2026-06-05 09:18:58.943136+07	2026-06-05 09:19:30.961758+07	lifecycle:picking:confirmed	mq0apjp3enamnnn2t8u	A06
1589	8bde631b	AGV01	go_to	17	completed	2026-06-05 09:18:45.028906+07	2026-06-05 09:19:12.445769+07	2026-06-05 09:19:37.302187+07	lifecycle:picking:confirmed	mq0ap8xuew993c678nh	A06
1590	df82d088	AGV01	go_charge	\N	cancelled	2026-06-05 09:18:45.039001+07	2026-06-05 09:19:37.302187+07	2026-06-05 09:24:00.364567+07	force-cancelled by user	mq0ap8xuew993c678nh	A06
1595	50857b5f	AGV01	go_charge	\N	cancelled	2026-06-05 09:19:37.320182+07	\N	2026-06-05 09:24:00.364567+07	cancelled by user	mq0ap8xuew993c678nh	A06
1596	66c1fb9e	AGV01	go_to	18	cancelled	2026-06-05 09:20:03.066931+07	\N	2026-06-05 09:24:00.364567+07	cancelled by user	mq0ap8xuew993c678nh	A06
1597	b7e0ceaa	AGV01	go_charge	\N	cancelled	2026-06-05 09:24:07.632668+07	2026-06-05 09:24:07.632668+07	2026-06-05 09:24:18.496281+07	force-cancelled by user	mq0aw5vqub1en8dhbyo	Sạc Pin
1788	b7bccff2	AGV01	go_to	17	completed	2026-06-05 11:31:43.904432+07	2026-06-05 11:31:43.904432+07	2026-06-05 11:32:18.855392+07	lifecycle:picking:confirmed	mq0fg9hwkors0qb8rk	A06
1662	86d6774e	AGV02	go_to	17	completed	2026-06-05 09:56:09.630856+07	2026-06-05 09:56:40.157029+07	2026-06-05 09:57:22.325106+07		mq0c1cn5xh357t2eg5	A06
1870	c303c644	AGV01	go_to	17	completed	2026-06-05 11:56:04.132598+07	2026-06-05 11:56:53.12784+07	2026-06-05 11:57:45.447374+07	lifecycle:picking:confirmed	mq0gbk66m0sxre51we	A06
1664	533c6de8	AGV02	go_to	17	completed	2026-06-05 09:56:40.173015+07	2026-06-05 09:57:22.327124+07	2026-06-05 09:57:40.860378+07		mq0c1cn5xh357t2eg5	A06
1663	c0e3f4de	AGV02	go_charge	\N	completed	2026-06-05 09:56:09.651823+07	2026-06-05 10:02:27.661216+07	2026-06-05 10:02:42.542474+07		mq0c1cn5xh357t2eg5	A06
1792	8001f83e	AGV02	go_to	17	completed	2026-06-05 11:31:59.971497+07	2026-06-05 11:32:47.030891+07	2026-06-05 11:33:03.333114+07		mq0fglvt3birpc9khno	A06
1872	5aa400e0	AGV01	go_to	17	cancelled	2026-06-05 11:56:21.134821+07	\N	2026-06-05 13:16:03.02073+07	cancelled by user	mq0gbxca5hut7tdbuep	A06
1794	6a2fdac3	AGV02	go_to	17	completed	2026-06-05 11:32:47.058888+07	2026-06-05 11:33:03.334114+07	2026-06-05 11:33:17.701634+07		mq0fglvt3birpc9khno	A06
1793	f7af39cf	AGV02	go_charge	\N	cancelled	2026-06-05 11:31:59.981493+07	\N	2026-06-05 11:37:23.16681+07	cancelled by user	mq0fglvt3birpc9khno	A06
1874	0eb99b42	AGV02	go_to	17	failed	2026-06-05 11:56:43.99288+07	2026-06-05 11:56:43.99288+07	2026-06-05 11:56:44.016121+07	cannot unpack non-iterable int object	mq0gcez76yp53wg95ok	A06
1885	3e6a58ba	AGV02	go_to	64	cancelled	2026-06-05 11:58:55.546517+07	\N	2026-06-05 13:15:57.743137+07	cancelled by user	mq0gdcv6i0rfqs3k0kd	A06
1869	74497802	AGV01	go_to	17	completed	2026-06-05 11:56:04.08003+07	2026-06-05 11:56:04.08003+07	2026-06-05 11:56:53.12784+07	lifecycle:picking:confirmed	mq0gbk66m0sxre51we	A06
1875	2b73fb54	AGV02	go_charge	\N	completed	2026-06-05 11:56:44.032103+07	2026-06-05 11:56:44.032103+07	2026-06-05 11:57:17.050864+07	charge_arrived	mq0gcez76yp53wg95ok	A06
1884	de0b9a9f	AGV02	go_to	19	cancelled	2026-06-05 11:58:46.168952+07	\N	2026-06-05 13:15:57.743137+07	cancelled by user	mq0gdcv6i0rfqs3k0kd	A06
1878	0d0f4088	AGV02	go_to	4	completed	2026-06-05 11:57:28.001315+07	2026-06-05 11:58:00.594467+07	2026-06-05 11:58:14.54913+07	lifecycle:picking:confirmed	mq0gdcv6i0rfqs3k0kd	A06
1883	d520ccc4	AGV02	go_to	9	cancelled	2026-06-05 11:58:39.163734+07	\N	2026-06-05 13:15:57.743137+07	cancelled by user	mq0gdcv6i0rfqs3k0kd	A06
1881	c8c74f26	AGV02	go_to	4	completed	2026-06-05 11:58:00.729243+07	2026-06-05 11:58:14.54913+07	2026-06-05 11:58:24.051469+07	lifecycle:picking:confirmed	mq0gdcv6i0rfqs3k0kd	A06
1882	b3e52c56	AGV02	go_to	17	cancelled	2026-06-05 11:58:24.075995+07	\N	2026-06-05 13:15:57.743137+07	cancelled by user	mq0gdcv6i0rfqs3k0kd	A06
1879	0b78f011	AGV02	go_charge	\N	cancelled	2026-06-05 11:57:28.019319+07	\N	2026-06-05 13:15:57.743137+07	cancelled by user	mq0gdcv6i0rfqs3k0kd	A06
1871	ac847b41	AGV01	go_charge	\N	cancelled	2026-06-05 11:56:04.147842+07	2026-06-05 11:57:45.447374+07	2026-06-05 13:16:03.01373+07	force-cancelled by user	mq0gbk66m0sxre51we	A06
1873	fa4053c1	AGV01	go_charge	\N	cancelled	2026-06-05 11:56:21.159824+07	\N	2026-06-05 13:16:03.02073+07	cancelled by user	mq0gbxca5hut7tdbuep	A06
1913	d8450ba7	AGV01	go_charge	\N	completed	2026-06-05 13:58:14.930296+07	2026-06-05 13:59:12.970765+07	2026-06-05 13:59:12.987707+07	bounce_wait	mq0koom8exeq5hkxgx	A06
1914	d3f07e9e	AGV02	go_to	17	completed	2026-06-05 13:58:32.747682+07	2026-06-05 13:58:32.747682+07	2026-06-05 13:59:05.995245+07	lifecycle:picking:confirmed	mq0kp2g6y1jfwj5fq7p	A06
1912	c7268c46	AGV01	go_to	17	completed	2026-06-05 13:58:14.908301+07	2026-06-05 13:58:48.834987+07	2026-06-05 13:59:12.970765+07	lifecycle:picking:confirmed	mq0koom8exeq5hkxgx	A06
1920	5ab217db	AGV02	go_charge	\N	completed	2026-06-05 14:00:21.353056+07	2026-06-05 14:00:36.056019+07	2026-06-05 14:01:18.187288+07	charge_arrived	mq0kp2g6y1jfwj5fq7p	A06
1103	7f83e8f9	AGV02	go_to	17	queued	2026-06-03 15:11:22.395494+07	\N	\N	\N	mpxsedyeya1skksgoa	A06
1111	6e0a4969	AGV01	go_to	17	completed	2026-06-03 15:27:14.955306+07	2026-06-03 15:27:14.955306+07	2026-06-03 15:27:47.586046+07	lifecycle:picking:confirmed	mpxszfr1909vhs8n21m	A06
1115	c695b49c	AGV02	go_to	17	cancelled	2026-06-03 15:27:35.275075+07	2026-06-03 15:28:03.80841+07	2026-06-03 15:35:31.239412+07	force-cancelled by user	mpxszvewup2seay74ld	A06
1171	4181c551	AGV01	go_to	19	cancelled	2026-06-03 15:35:37.837031+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1114	016438af	AGV02	go_to	17	completed	2026-06-03 15:27:35.24707+07	2026-06-03 15:27:35.24707+07	2026-06-03 15:28:03.807408+07	lifecycle:picking:confirmed	mpxszvewup2seay74ld	A06
1112	c8599fc7	AGV01	go_to	17	completed	2026-06-03 15:27:15.008374+07	2026-06-03 15:27:47.586046+07	2026-06-03 15:28:16.096978+07	lifecycle:picking:confirmed	mpxszfr1909vhs8n21m	A06
1116	669957ad	AGV02	go_charge	\N	cancelled	2026-06-03 15:27:35.295072+07	\N	2026-06-03 15:35:31.239412+07	cancelled by user	mpxszvewup2seay74ld	A06
1113	701ea870	AGV01	go_charge	\N	completed	2026-06-03 15:27:15.025408+07	2026-06-03 15:28:16.096978+07	2026-06-03 15:28:21.30435+07		mpxszfr1909vhs8n21m	A06
1162	96aae80e	AGV01	go_to	9	cancelled	2026-06-03 15:34:26.723715+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1326	5020fc9e	AGV01	go_charge	\N	cancelled	2026-06-03 16:48:25.80782+07	2026-06-03 16:48:25.80782+07	2026-06-03 16:48:47.014972+07	force-cancelled by user	mpxvvu4qii0sbhq6b0c	Sạc Pin
1328	88831779	AGV01	go_charge	\N	completed	2026-06-03 16:48:53.794886+07	2026-06-03 16:48:53.794886+07	2026-06-03 16:48:57.457668+07		mpxvwfq88vy2kie036o	Sạc Pin
1329	3f2cf963	AGV01	go_charge	\N	completed	2026-06-03 16:48:53.805882+07	2026-06-03 16:48:57.46567+07	2026-06-03 16:49:41.685582+07	charge_arrived	mpxvwfq88vy2kie036o	Sạc Pin
1382	7a92ac37	AGV01	go_to	17	completed	2026-06-04 09:00:17.09854+07	2026-06-04 09:00:17.09854+07	2026-06-04 09:00:47.880827+07	event:continue	mpyulne9844ahpom2oj	A06
3578	2b76eed1	AGV01	go_to	18	cancelled	2026-07-08 14:43:14.834229+07	2026-07-08 14:43:14.835229+07	2026-07-08 14:43:21.53842+07	force-cancelled by user	\N	\N
1117	8867c505	AGV02	go_to	17	cancelled	2026-06-03 15:28:03.811412+07	\N	2026-06-03 15:35:31.239412+07	cancelled by user	mpxszvewup2seay74ld	A06
1118	9e3516c2	AGV01	go_charge	\N	cancelled	2026-06-03 15:28:16.112995+07	2026-06-03 15:28:21.306352+07	2026-06-03 15:35:40.53897+07	force-cancelled by user	mpxszfr1909vhs8n21m	A06
1170	0c8dc438	AGV01	go_to	9	cancelled	2026-06-03 15:35:28.456497+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1161	e23e5b41	AGV01	go_to	19	cancelled	2026-06-03 15:34:17.491135+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1160	4d9ce121	AGV01	go_to	9	cancelled	2026-06-03 15:34:08.261763+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1159	8c02bbff	AGV01	go_to	19	cancelled	2026-06-03 15:33:59.030663+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1158	ac3ad859	AGV01	go_to	9	cancelled	2026-06-03 15:33:51.890768+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1157	ac853e14	AGV01	go_to	19	cancelled	2026-06-03 15:33:44.753213+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1156	940b367b	AGV01	go_to	9	cancelled	2026-06-03 15:33:37.747256+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1155	011203a7	AGV01	go_to	19	cancelled	2026-06-03 15:33:30.70931+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1154	61b2f920	AGV01	go_to	9	cancelled	2026-06-03 15:33:21.348369+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1153	9f2e8f86	AGV01	go_to	19	cancelled	2026-06-03 15:33:12.097139+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1152	a654ac40	AGV01	go_to	9	cancelled	2026-06-03 15:33:02.86697+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1151	98998438	AGV01	go_to	19	cancelled	2026-06-03 15:32:53.632371+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1150	ba43bc6a	AGV01	go_to	9	cancelled	2026-06-03 15:32:46.642196+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1149	ae11b326	AGV01	go_to	19	cancelled	2026-06-03 15:32:39.541098+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1148	c79eeb03	AGV01	go_to	9	cancelled	2026-06-03 15:32:32.483388+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1147	2c80c18b	AGV01	go_to	19	cancelled	2026-06-03 15:32:25.366693+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1146	fb5db692	AGV01	go_to	9	cancelled	2026-06-03 15:32:18.296708+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1145	4d97bcbc	AGV01	go_to	19	cancelled	2026-06-03 15:32:11.322739+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1144	46b5992b	AGV01	go_to	9	cancelled	2026-06-03 15:32:04.228152+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1143	0d09d0f3	AGV01	go_to	19	cancelled	2026-06-03 15:31:54.933066+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1142	fb139ed5	AGV01	go_to	9	cancelled	2026-06-03 15:31:47.948689+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1141	2d7c994a	AGV01	go_to	19	cancelled	2026-06-03 15:31:38.690258+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1140	b53a1d84	AGV01	go_to	9	cancelled	2026-06-03 15:31:31.700131+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1138	3a7deaf7	AGV01	go_to	9	cancelled	2026-06-03 15:31:13.241351+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1137	d5d9345b	AGV01	go_to	19	cancelled	2026-06-03 15:31:04.051726+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1136	96fa85e6	AGV01	go_to	9	cancelled	2026-06-03 15:30:56.870192+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1135	39d603c3	AGV01	go_to	19	cancelled	2026-06-03 15:30:49.742336+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1132	55193487	AGV01	go_to	9	cancelled	2026-06-03 15:30:27.409878+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1131	b6e26366	AGV01	go_to	19	cancelled	2026-06-03 15:30:18.196399+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1130	a0717885	AGV01	go_to	9	cancelled	2026-06-03 15:30:08.946064+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1129	c0f26765	AGV01	go_to	19	cancelled	2026-06-03 15:30:01.834383+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1128	2cc7c029	AGV01	go_to	9	cancelled	2026-06-03 15:29:54.77392+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1127	dbc67505	AGV01	go_to	19	cancelled	2026-06-03 15:29:45.907686+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1126	4f772fcf	AGV01	go_to	9	cancelled	2026-06-03 15:29:38.898859+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1123	ea5761b6	AGV01	go_to	19	cancelled	2026-06-03 15:29:13.948878+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1122	8e8cc6be	AGV01	go_to	9	cancelled	2026-06-03 15:29:04.720456+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1121	855b0181	AGV01	go_to	19	cancelled	2026-06-03 15:28:56.543168+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1120	cd93eee6	AGV01	go_to	9	cancelled	2026-06-03 15:28:49.367099+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1169	93d3b058	AGV01	go_to	19	cancelled	2026-06-03 15:35:21.481294+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1167	d6099cbb	AGV01	go_to	19	cancelled	2026-06-03 15:35:07.470959+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1139	fc7eefc2	AGV01	go_to	19	cancelled	2026-06-03 15:31:22.464492+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1125	71120d12	AGV01	go_to	19	cancelled	2026-06-03 15:29:31.90226+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1119	37f4efdc	AGV01	go_to	13	cancelled	2026-06-03 15:28:42.366514+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1327	5dabe34b	AGV01	go_charge	\N	cancelled	2026-06-03 16:48:25.820877+07	\N	2026-06-03 16:48:47.014972+07	cancelled by user	mpxvvu4qii0sbhq6b0c	Sạc Pin
1384	2a8a7073	AGV01	go_charge	\N	queued	2026-06-04 09:00:17.372901+07	\N	\N	\N	mpyulne9844ahpom2oj	A06
1387	475a6480	AGV02	go_charge	\N	queued	2026-06-04 09:00:29.13202+07	\N	\N	\N	mpyulwo1w0ranpuqhub	A06
1383	9e0fd2ff	AGV01	go_to	17	running	2026-06-04 09:00:17.354687+07	2026-06-04 09:00:47.881837+07	\N		mpyulne9844ahpom2oj	A06
1386	a41d44c9	AGV02	go_to	17	running	2026-06-04 09:00:29.116619+07	2026-06-04 09:00:59.104408+07	\N		mpyulwo1w0ranpuqhub	A06
1385	1a7066d7	AGV02	go_to	17	completed	2026-06-04 09:00:29.094134+07	2026-06-04 09:00:29.094134+07	2026-06-04 09:00:59.101413+07	event:continue	mpyulwo1w0ranpuqhub	A06
1388	598066a8	AGV02	go_to	17	queued	2026-06-04 09:01:30.796496+07	\N	\N	\N	mpyulwo1w0ranpuqhub	A06
1389	efd2c5a2	AGV02	go_to	5	queued	2026-06-04 09:01:37.784496+07	\N	\N	\N	mpyulwo1w0ranpuqhub	A06
1390	4674a014	AGV02	go_to	19	queued	2026-06-04 09:01:44.830561+07	\N	\N	\N	mpyulwo1w0ranpuqhub	A06
1737	9c6a746e	AGV02	go_charge	\N	cancelled	2026-06-05 10:41:53.742807+07	\N	2026-06-05 10:42:00.575438+07	cancelled by user	mq0do68q7oovig9b2sa	Sạc Pin
1463	1ceeba5b	AGV01	go_to	17	completed	2026-06-04 10:32:44.435178+07	2026-06-04 10:32:44.435178+07	2026-06-04 10:33:14.399373+07	lifecycle:picking:confirmed	mpyxwjrf8xb04kw76s	A06
1464	2daa93ff	AGV01	go_to	17	completed	2026-06-04 10:32:44.632883+07	2026-06-04 10:33:14.408374+07	2026-06-04 10:33:38.40702+07	lifecycle:picking:confirmed	mpyxwjrf8xb04kw76s	A06
1467	be5873c2	AGV02	go_to	17	completed	2026-06-04 10:33:10.228058+07	2026-06-04 10:34:04.534829+07	2026-06-04 10:35:36.393236+07	lifecycle:picking:confirmed	mpyxx3m5abt1y3d25u6	A06
1468	f740c0df	AGV02	go_charge	\N	completed	2026-06-04 10:33:10.271629+07	2026-06-04 10:35:36.397237+07	2026-06-04 10:35:42.486948+07		mpyxx3m5abt1y3d25u6	A06
1475	3806897e	AGV02	go_to	17	completed	2026-06-04 10:37:27.788056+07	2026-06-04 10:37:27.788056+07	2026-06-04 10:37:56.159372+07	lifecycle:picking:confirmed	mpyy2mednidvd18m759	A06
1473	5b1874ac	AGV01	go_to	17	completed	2026-06-04 10:37:02.532468+07	2026-06-04 10:37:34.48074+07	2026-06-04 10:38:18.409562+07	lifecycle:picking:confirmed	mpyy22w4bodpj0ya33f	A06
1928	6fbc837b	AGV02	go_charge	\N	completed	2026-06-05 14:02:50.941549+07	2026-06-05 14:02:50.941549+07	2026-06-05 14:02:50.951534+07	bounce_wait	\N	bounce_retry
1474	41e4744d	AGV01	go_charge	\N	completed	2026-06-04 10:37:02.541472+07	2026-06-04 10:38:18.409562+07	2026-06-04 10:38:27.731636+07		mpyy22w4bodpj0ya33f	A06
1512	c5f5810d	AGV01	go_charge	\N	cancelled	2026-06-04 15:54:03.022286+07	2026-06-04 15:54:08.384146+07	2026-06-04 16:01:43.92582+07	force-cancelled by user	mpz9dr7876snp8u8z8r	Sạc Pin
1789	2be561b1	AGV01	go_to	17	completed	2026-06-05 11:31:44.324953+07	2026-06-05 11:32:18.855392+07	2026-06-05 11:32:40.75033+07	lifecycle:picking:confirmed	mq0fg9hwkors0qb8rk	A06
1790	debf742c	AGV01	go_charge	\N	completed	2026-06-05 11:31:44.340283+07	2026-06-05 11:32:40.75033+07	2026-06-05 11:32:40.767321+07	bounce_wait	mq0fg9hwkors0qb8rk	A06
1574	07e11c98	AGV02	go_to	17	completed	2026-06-05 09:13:10.668272+07	2026-06-05 09:13:43.179479+07	2026-06-05 09:14:27.055282+07	lifecycle:picking:confirmed	mq0ai2psanec35p5cqk	A06
1576	2bb0127d	AGV01	go_to	17	cancelled	2026-06-05 09:13:28.202039+07	2026-06-05 09:13:28.202039+07	2026-06-05 09:14:42.724707+07	force-cancelled by user	mq0aighzosjik0o4cxh	A06
1575	da5be270	AGV02	go_charge	\N	completed	2026-06-05 09:13:10.683276+07	2026-06-05 09:14:27.056296+07	2026-06-05 09:14:47.81761+07		mq0ai2psanec35p5cqk	A06
1588	34abaf20	AGV01	go_to	17	completed	2026-06-05 09:18:45.000593+07	2026-06-05 09:18:45.000593+07	2026-06-05 09:19:12.436769+07	lifecycle:picking:confirmed	mq0ap8xuew993c678nh	A06
1791	5fd4a1f5	AGV02	go_to	17	completed	2026-06-05 11:31:59.951956+07	2026-06-05 11:31:59.951956+07	2026-06-05 11:32:47.030891+07	lifecycle:picking:confirmed	mq0fglvt3birpc9khno	A06
1592	66bf40b9	AGV02	go_to	17	completed	2026-06-05 09:18:59.217592+07	2026-06-05 09:19:30.961758+07	2026-06-05 09:20:14.376924+07		mq0apjp3enamnnn2t8u	A06
1593	eb8184b3	AGV02	go_charge	\N	completed	2026-06-05 09:18:59.23158+07	2026-06-05 09:24:22.071323+07	2026-06-05 09:25:44.929094+07	charge_arrived	mq0apjp3enamnnn2t8u	A06
1795	7a7cfa96	AGV01	go_charge	\N	completed	2026-06-05 11:33:03.334114+07	2026-06-05 11:33:03.334114+07	2026-06-05 11:33:03.417627+07	bounce_wait	\N	bounce_retry
1665	96a6cb8b	AGV01	go_charge	\N	completed	2026-06-05 09:56:49.799307+07	2026-06-05 09:57:08.095152+07	2026-06-05 09:57:53.004031+07	charge_arrived	mq0c0ypbw4ol00oy2h	A06
1666	99339970	AGV02	go_to	17	completed	2026-06-05 09:57:22.429675+07	2026-06-05 09:57:40.862346+07	2026-06-05 10:02:05.745977+07	lifecycle:picking:confirmed	mq0c1cn5xh357t2eg5	A06
1797	511a58b1	AGV01	go_charge	\N	cancelled	2026-06-05 11:33:17.702621+07	2026-06-05 11:33:17.702621+07	2026-06-05 11:37:29.888038+07	force-cancelled by user	\N	bounce_retry
1876	29c172f1	AGV02	go_to	17	completed	2026-06-05 11:57:27.910253+07	2026-06-05 11:57:27.910253+07	2026-06-05 11:58:00.58547+07	lifecycle:picking:confirmed	mq0gdcv6i0rfqs3k0kd	A06
1929	c1dbf930	AGV02	go_charge	\N	completed	2026-06-05 14:04:52.141479+07	2026-06-05 14:04:52.141479+07	2026-06-05 14:04:52.15746+07	bounce_wait	mq0kx76v4mwg9t2oy9	Sạc Pin
1877	eab7d185	AGV02	go_to	17	cancelled	2026-06-05 11:57:27.951278+07	2026-06-05 11:58:24.051469+07	2026-06-05 13:15:57.743137+07	force-cancelled by user	mq0gdcv6i0rfqs3k0kd	A06
1918	220094de	AGV01	go_charge	\N	completed	2026-06-05 13:59:16.820269+07	2026-06-05 13:59:16.820269+07	2026-06-05 13:59:32.250841+07		\N	bounce_retry
1927	739c1261	AGV01	go_to	17	cancelled	2026-06-05 14:02:32.366507+07	\N	2026-06-05 14:06:04.212692+07	cancelled by user	mq0kta5chrlenp08cs	A06
1922	78cb59bc	AGV02	go_to	17	completed	2026-06-05 14:01:40.177327+07	2026-06-05 14:02:08.29363+07	2026-06-05 14:02:28.961996+07	lifecycle:picking:confirmed	mq0kt321uakrafem32	A06
1923	6b67761c	AGV02	go_charge	\N	completed	2026-06-05 14:01:40.187315+07	2026-06-05 14:02:28.961996+07	2026-06-05 14:02:28.979001+07	bounce_wait	mq0kt321uakrafem32	A06
1924	d1aa1eaa	AGV01	go_to	17	completed	2026-06-05 14:01:49.357642+07	2026-06-05 14:01:49.357642+07	2026-06-05 14:02:32.187436+07	lifecycle:picking:confirmed	mq0kta5chrlenp08cs	A06
1999	7fd60208	AGV02	go_to	96	completed	2026-06-06 09:36:07.111142+07	2026-06-06 09:36:34.427395+07	2026-06-06 09:36:49.904412+07		mq1qrfmxrwxscfgmrf	A02
1933	3a03fdf7	AGV02	go_charge	\N	completed	2026-06-05 14:06:26.388406+07	2026-06-05 14:06:40.894321+07	2026-06-05 14:07:27.22809+07	charge_arrived	\N	bounce_retry
1948	14361249	AGV02	go_to	69	completed	2026-06-05 15:40:21.045092+07	2026-06-05 15:40:21.045092+07	2026-06-05 15:40:51.143746+07	lifecycle:picking:confirmed	mq0obzmvod6h3vlol2	A06
1966	7f6bcbec	AGV02	go_to	17	cancelled	2026-06-05 15:58:30.945092+07	\N	2026-06-05 16:00:56.287899+07	cancelled by user	mq0ozclas3up3vfyj4q	A02
1967	69dbf979	AGV02	go_charge	\N	cancelled	2026-06-05 15:58:30.956089+07	\N	2026-06-05 16:00:56.287899+07	cancelled by user	mq0ozclas3up3vfyj4q	A02
1991	5fed9708	AGV02	go_to	69	completed	2026-06-05 16:23:08.156717+07	2026-06-05 16:23:25.503932+07	2026-06-05 16:56:43.08667+07	lifecycle:picking:confirmed	mq0prigz87ferr8gtgn	A06
2011	4ac5c670	AGV01	go_to	18	completed	2026-06-06 09:53:12.779406+07	2026-06-06 09:53:12.779406+07	2026-06-06 09:53:46.378305+07	lifecycle:picking:confirmed	mq1rdf47fxabgdfeun	A02
2001	4954711c	AGV02	go_charge	\N	completed	2026-06-06 09:36:07.13712+07	2026-06-06 09:39:31.367004+07	2026-06-06 09:40:17.277618+07	charge_arrived	mq1qrfmxrwxscfgmrf	A02
2000	3e78d3cc	AGV02	go_to	69	completed	2026-06-06 09:36:07.121129+07	2026-06-06 09:37:08.607764+07	2026-06-06 09:37:35.341312+07	off_route	mq1qrfmxrwxscfgmrf	A02
2008	f270f57f	AGV02	go_charge	\N	completed	2026-06-06 09:50:30.349788+07	2026-06-06 09:52:04.505898+07	2026-06-06 09:52:17.849572+07		mq1r9xlxijx6nobimq	A02
2028	149340e7	AGV02	go_to	64	completed	2026-06-06 11:02:35.384003+07	2026-06-06 11:02:35.384003+07	2026-06-06 11:03:10.791077+07	lifecycle:picking:confirmed	mq1tum5wpi2jdka25ri	A02
2024	2a3614ab	AGV02	go_to	64	cancelled	2026-06-06 10:16:49.083227+07	2026-06-06 10:17:03.804741+07	2026-06-06 10:55:36.805355+07	force-cancelled by user	mq1s6ka7y9ki2n4sych	A02
2029	b6cfc2f8	AGV02	go_to	18	completed	2026-06-06 11:02:35.563186+07	2026-06-06 11:03:25.035938+07	2026-06-06 11:03:46.68971+07	lifecycle:picking:confirmed	mq1tum5wpi2jdka25ri	A02
2788	c84ce056	AGV02	go_charge	\N	completed	2026-06-15 10:54:27.585337+07	2026-06-15 10:57:27.870685+07	2026-06-15 10:57:37.976975+07	off_route	mqeoitsrvggghgun36h	A06
2035	c6f4c050	AGV02	go_charge	14	completed	2026-06-06 11:06:57.468144+07	2026-06-06 11:06:57.469137+07	2026-06-06 11:07:18.293459+07		mq1u02s76ouo4yfrnlm	Sạc Pin
1134	76f78b35	AGV01	go_to	9	cancelled	2026-06-03 15:30:41.558536+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1133	3f6c73ed	AGV01	go_to	19	cancelled	2026-06-03 15:30:34.421666+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1124	936c1430	AGV01	go_to	9	cancelled	2026-06-03 15:29:20.941993+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1165	f48d639a	AGV01	go_to	19	cancelled	2026-06-03 15:34:49.960765+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1164	4e4703a6	AGV01	go_to	9	cancelled	2026-06-03 15:34:42.944402+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1163	7c1e4d4b	AGV01	go_to	19	cancelled	2026-06-03 15:34:33.77866+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1166	63983492	AGV01	go_to	9	cancelled	2026-06-03 15:34:59.167276+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1168	3da1768e	AGV01	go_to	9	cancelled	2026-06-03 15:35:14.470642+07	\N	2026-06-03 15:35:40.53897+07	cancelled by user	mpxszfr1909vhs8n21m	A06
1191	e6584e58	AGV02	go_charge	\N	completed	2026-06-03 15:47:07.252629+07	2026-06-03 15:47:07.252629+07	2026-06-03 15:47:08.928763+07	charge_arrived	mpxtozpkvgaw036lf1b	A06
1172	3a580f3b	AGV01	go_to	17	completed	2026-06-03 15:39:53.535433+07	2026-06-03 15:39:53.535433+07	2026-06-03 15:40:24.747367+07	lifecycle:picking:confirmed	mpxtfp2qsotl98is13s	A06
1175	36956565	AGV02	go_to	17	completed	2026-06-03 15:40:11.17193+07	2026-06-03 15:40:11.17193+07	2026-06-03 15:40:46.400502+07	lifecycle:picking:confirmed	mpxtg2ouhzdksc78694	A06
1173	819faa34	AGV01	go_to	17	completed	2026-06-03 15:39:53.602755+07	2026-06-03 15:40:24.747367+07	2026-06-03 15:41:16.70453+07	event:continue	mpxtfp2qsotl98is13s	A06
1192	f58410ec	AGV02	go_to	18	failed	2026-06-03 15:47:21.897196+07	2026-06-03 15:47:21.897196+07	2026-06-03 15:47:21.909218+07	name 'conflict_set' is not defined	mpxtpb1i6za0563mixs	A06
1174	7b0ae038	AGV01	go_charge	\N	completed	2026-06-03 15:39:53.626041+07	2026-06-03 15:41:16.706525+07	2026-06-03 15:41:27.050782+07		mpxtfp2qsotl98is13s	A06
1178	dcc32c8a	AGV01	go_charge	\N	completed	2026-06-03 15:41:16.724523+07	2026-06-03 15:41:27.051781+07	2026-06-03 15:42:11.311634+07	charge_arrived	mpxtfp2qsotl98is13s	A06
1176	957a0f4f	AGV02	go_to	17	completed	2026-06-03 15:40:11.190152+07	2026-06-03 15:40:46.400502+07	2026-06-03 15:42:12.622419+07	lifecycle:picking:confirmed	mpxtg2ouhzdksc78694	A06
1193	6c4f8be9	AGV02	go_charge	\N	completed	2026-06-03 15:47:21.921722+07	2026-06-03 15:47:21.921722+07	2026-06-03 15:47:23.595485+07	charge_arrived	mpxtpb1i6za0563mixs	A06
1177	70dac444	AGV02	go_charge	\N	completed	2026-06-03 15:40:11.201169+07	2026-06-03 15:42:12.622419+07	2026-06-03 15:42:54.297898+07	charge_arrived	mpxtg2ouhzdksc78694	A06
1179	9d654e21	AGV01	go_to	17	completed	2026-06-03 15:43:21.191641+07	2026-06-03 15:43:21.191641+07	2026-06-03 15:43:56.300732+07	event:continue	mpxtk5b5eda4l3abw0m	A06
1189	85ceac24	AGV01	go_charge	\N	completed	2026-06-03 15:47:01.402453+07	2026-06-03 15:47:06.609247+07	2026-06-03 15:48:42.453962+07	event:continue	mpxtnu8wpk8e42xfkej	A06
1182	6e4a0a9a	AGV02	go_to	17	completed	2026-06-03 15:43:36.730458+07	2026-06-03 15:43:36.730458+07	2026-06-03 15:44:09.851159+07	event:continue	mpxtkhat0bwmfbhh2uvb	A06
1180	cf18df3b	AGV01	go_to	17	completed	2026-06-03 15:43:21.414251+07	2026-06-03 15:43:56.301748+07	2026-06-03 15:44:13.638803+07	event:continue	mpxtk5b5eda4l3abw0m	A06
1194	69e341bf	AGV01	go_charge	\N	completed	2026-06-03 15:49:24.136135+07	2026-06-03 15:49:24.136135+07	2026-06-03 15:50:03.129805+07	charge_arrived	mpxtrxcxdg3imoppgcq	Sạc Pin
1181	63639f44	AGV01	go_charge	\N	completed	2026-06-03 15:43:21.426259+07	2026-06-03 15:44:13.640786+07	2026-06-03 15:44:18.892023+07		mpxtk5b5eda4l3abw0m	A06
1185	ce7e71b6	AGV01	go_charge	\N	completed	2026-06-03 15:44:13.653299+07	2026-06-03 15:44:18.892023+07	2026-06-03 15:45:12.896691+07	charge_arrived	mpxtk5b5eda4l3abw0m	A06
1183	6e0576d1	AGV02	go_to	17	completed	2026-06-03 15:43:36.755466+07	2026-06-03 15:44:09.859157+07	2026-06-03 15:45:20.027332+07	event:continue	mpxtkhat0bwmfbhh2uvb	A06
1184	d2c27617	AGV02	go_charge	\N	completed	2026-06-03 15:43:36.770453+07	2026-06-03 15:45:20.027332+07	2026-06-03 15:46:01.583101+07	charge_arrived	mpxtkhat0bwmfbhh2uvb	A06
1186	f7ddaf30	AGV01	go_to	17	completed	2026-06-03 15:46:13.477922+07	2026-06-03 15:46:13.477922+07	2026-06-03 15:46:44.581984+07	lifecycle:picking:confirmed	mpxtnu8wpk8e42xfkej	A06
1195	22694406	AGV01	go_to	17	completed	2026-06-03 15:50:46.507098+07	2026-06-03 15:50:46.507098+07	2026-06-03 15:51:16.739721+07	lifecycle:picking:confirmed	mpxttowpa0wq6ipjqh	A06
1187	630a759c	AGV01	go_to	17	completed	2026-06-03 15:46:13.506529+07	2026-06-03 15:46:44.582985+07	2026-06-03 15:47:01.384934+07	lifecycle:picking:confirmed	mpxtnu8wpk8e42xfkej	A06
1188	c9d2729c	AGV01	go_charge	\N	completed	2026-06-03 15:46:13.513992+07	2026-06-03 15:47:01.385937+07	2026-06-03 15:47:06.608239+07		mpxtnu8wpk8e42xfkej	A06
1190	30122075	AGV02	go_to	17	failed	2026-06-03 15:47:07.215116+07	2026-06-03 15:47:07.215116+07	2026-06-03 15:47:07.232646+07	name 'conflict_set' is not defined	mpxtozpkvgaw036lf1b	A06
1202	10b3e990	AGV01	go_to	17	completed	2026-06-03 15:52:51.543738+07	2026-06-03 15:52:51.543738+07	2026-06-03 15:53:26.7674+07	lifecycle:picking:confirmed	mpxtwddyh043pnizbul	A06
1205	ec561cdf	AGV02	go_to	17	completed	2026-06-03 15:53:16.3877+07	2026-06-03 15:53:16.3877+07	2026-06-03 15:53:43.918664+07	lifecycle:picking:confirmed	mpxtwwkefhkvbwe8dhi	A06
1196	d5ab14e3	AGV01	go_to	17	completed	2026-06-03 15:50:46.713453+07	2026-06-03 15:51:16.74872+07	2026-06-03 15:51:33.099327+07	lifecycle:picking:confirmed	mpxttowpa0wq6ipjqh	A06
1197	2863cb76	AGV01	go_charge	\N	completed	2026-06-03 15:50:46.723453+07	2026-06-03 15:51:33.110316+07	2026-06-03 15:51:42.879554+07		mpxttowpa0wq6ipjqh	A06
1206	f12925f4	AGV02	go_to	17	running	2026-06-03 15:53:16.414774+07	2026-06-03 15:53:43.918664+07	\N		mpxtwwkefhkvbwe8dhi	A06
1198	adcffb64	AGV01	go_charge	\N	completed	2026-06-03 15:51:33.262186+07	2026-06-03 15:51:42.881554+07	2026-06-03 15:52:28.784304+07	charge_arrived	mpxttowpa0wq6ipjqh	A06
1199	97258027	AGV02	go_to	18	cancelled	2026-06-03 15:51:49.596311+07	2026-06-03 15:51:49.596311+07	2026-06-03 15:52:35.345637+07	force-cancelled by user	mpxtv1lej3qvz36yma7	A06
1200	47544410	AGV02	go_to	18	cancelled	2026-06-03 15:51:49.61934+07	\N	2026-06-03 15:52:35.346637+07	cancelled by user	mpxtv1lej3qvz36yma7	A06
1201	ded6ca42	AGV02	go_charge	\N	cancelled	2026-06-03 15:51:49.666393+07	\N	2026-06-03 15:52:35.346637+07	cancelled by user	mpxtv1lej3qvz36yma7	A06
1207	bf977de7	AGV02	go_charge	\N	queued	2026-06-03 15:53:16.431774+07	\N	\N	\N	mpxtwwkefhkvbwe8dhi	A06
1208	46bda7eb	AGV02	go_to	17	queued	2026-06-03 15:53:43.921654+07	\N	\N	\N	mpxtwwkefhkvbwe8dhi	A06
1203	50bb1de0	AGV01	go_to	17	completed	2026-06-03 15:52:51.578879+07	2026-06-03 15:53:26.7674+07	2026-06-03 15:53:46.914239+07	lifecycle:picking:confirmed	mpxtwddyh043pnizbul	A06
1334	b0632280	AGV02	go_to	17	queued	2026-06-03 16:50:19.333833+07	\N	\N	\N	mpxvy9p3hw5ra7vad55	A06
1204	551404ad	AGV01	go_charge	\N	completed	2026-06-03 15:52:51.58888+07	2026-06-03 15:53:46.914239+07	2026-06-03 15:53:52.261736+07		mpxtwddyh043pnizbul	A06
1209	951795c1	AGV01	go_charge	\N	running	2026-06-03 15:53:46.930614+07	2026-06-03 15:53:52.26287+07	\N		mpxtwddyh043pnizbul	A06
1210	f857c694	AGV01	go_to	13	queued	2026-06-03 15:54:18.264027+07	\N	\N	\N	mpxtwddyh043pnizbul	A06
1211	b66aa972	AGV01	go_to	9	queued	2026-06-03 15:54:25.2435+07	\N	\N	\N	mpxtwddyh043pnizbul	A06
1212	d0f53099	AGV01	go_to	19	queued	2026-06-03 15:54:32.240972+07	\N	\N	\N	mpxtwddyh043pnizbul	A06
1213	e8776c6d	AGV01	go_to	9	queued	2026-06-03 15:54:39.32238+07	\N	\N	\N	mpxtwddyh043pnizbul	A06
1214	6d02594a	AGV01	go_to	19	queued	2026-06-03 15:54:46.483419+07	\N	\N	\N	mpxtwddyh043pnizbul	A06
1215	940cff7c	AGV01	go_to	9	queued	2026-06-03 15:54:55.752205+07	\N	\N	\N	mpxtwddyh043pnizbul	A06
1216	7ca0a0f1	AGV01	go_to	19	queued	2026-06-03 15:55:05.148398+07	\N	\N	\N	mpxtwddyh043pnizbul	A06
1335	a699f0b4	AGV02	go_charge	\N	queued	2026-06-03 16:50:19.351832+07	\N	\N	\N	mpxvy9p3hw5ra7vad55	A06
1330	116ff5a4	AGV01	go_to	17	completed	2026-06-03 16:50:06.99037+07	2026-06-03 16:50:06.99037+07	2026-06-03 16:50:35.241296+07	lifecycle:picking:confirmed	mpxvy06v87841djeqwi	A06
1336	7ebc53ea	AGV01	go_charge	\N	running	2026-06-03 16:50:55.413916+07	2026-06-03 16:51:00.749641+07	\N		mpxvy06v87841djeqwi	A06
2796	8d09796e	AGV02	go_to	5	completed	2026-06-15 10:57:37.975898+07	2026-06-15 10:57:37.977536+07	2026-06-15 10:57:51.847654+07		mqeoitsrvggghgun36h	A06
1217	0d50eedf	AGV01	go_to	9	queued	2026-06-03 15:55:12.136344+07	\N	\N	\N	mpxtwddyh043pnizbul	A06
1218	387c15cb	AGV01	go_to	19	queued	2026-06-03 15:55:21.382509+07	\N	\N	\N	mpxtwddyh043pnizbul	A06
1219	18a5a057	AGV01	go_to	9	queued	2026-06-03 15:55:28.399067+07	\N	\N	\N	mpxtwddyh043pnizbul	A06
1220	fa37b248	AGV02	go_charge	\N	cancelled	2026-06-03 15:58:08.306403+07	2026-06-03 15:58:08.306403+07	2026-06-03 15:58:20.888704+07	force-cancelled by user	mpxu35sxj5nx0js8v4	Sạc Pin
1222	87475c85	AGV02	go_to	3	cancelled	2026-06-03 15:58:15.148851+07	\N	2026-06-03 15:58:20.888704+07	cancelled by user	mpxu35sxj5nx0js8v4	Sạc Pin
1221	2813d0e2	AGV02	go_charge	\N	cancelled	2026-06-03 15:58:08.513189+07	\N	2026-06-03 15:58:20.888704+07	cancelled by user	mpxu35sxj5nx0js8v4	Sạc Pin
1223	f5069234	AGV01	go_charge	\N	completed	2026-06-03 15:59:05.56419+07	2026-06-03 15:59:05.56419+07	2026-06-03 15:59:10.785114+07		mpxu4dzt83lwcpnx04	Sạc Pin
1472	9f2a90ec	AGV01	go_to	17	completed	2026-06-04 10:37:02.512942+07	2026-06-04 10:37:02.512942+07	2026-06-04 10:37:34.48074+07	lifecycle:picking:confirmed	mpyy22w4bodpj0ya33f	A06
1224	18915ad5	AGV01	go_charge	\N	completed	2026-06-03 15:59:05.606191+07	2026-06-03 15:59:10.785114+07	2026-06-03 15:59:51.428313+07	charge_arrived	mpxu4dzt83lwcpnx04	Sạc Pin
1225	9ae1e3df	AGV01	go_to	17	completed	2026-06-03 16:01:03.474222+07	2026-06-03 16:01:03.474222+07	2026-06-03 16:01:33.420026+07	lifecycle:picking:confirmed	mpxu6wytbo8yyamjf8l	A06
1236	79fd0a27	AGV01	go_to	17	completed	2026-06-03 16:10:04.811152+07	2026-06-03 16:10:04.811152+07	2026-06-03 16:10:36.092802+07	lifecycle:picking:confirmed	mpxuiinuyclvxwhhi1	A06
1517	6850259f	AGV01	go_to	18	completed	2026-06-04 16:02:41.543015+07	2026-06-04 16:02:49.403775+07	2026-06-04 16:03:08.959326+07	event:continue	mpz9o7wi7bqkppnera9	A02
1228	dced55a6	AGV02	go_to	17	completed	2026-06-03 16:01:19.276643+07	2026-06-03 16:01:19.276643+07	2026-06-03 16:01:45.299869+07	lifecycle:picking:confirmed	mpxu795zpmo6tgrc5d	A06
1226	822d99a7	AGV01	go_to	17	completed	2026-06-03 16:01:03.667316+07	2026-06-03 16:01:33.420026+07	2026-06-03 16:01:59.554128+07	lifecycle:picking:confirmed	mpxu6wytbo8yyamjf8l	A06
1237	c55f002d	AGV01	go_to	17	completed	2026-06-03 16:10:04.853161+07	2026-06-03 16:10:36.104784+07	2026-06-03 16:10:57.13827+07	lifecycle:picking:confirmed	mpxuiinuyclvxwhhi1	A06
1227	a791b2b4	AGV01	go_charge	\N	completed	2026-06-03 16:01:03.691847+07	2026-06-03 16:01:59.554128+07	2026-06-03 16:02:04.971202+07		mpxu6wytbo8yyamjf8l	A06
1238	7b38b225	AGV01	go_charge	\N	completed	2026-06-03 16:10:04.866155+07	2026-06-03 16:10:57.13827+07	2026-06-03 16:11:02.363298+07		mpxuiinuyclvxwhhi1	A06
1231	7eb27f18	AGV01	go_charge	\N	completed	2026-06-03 16:01:59.570668+07	2026-06-03 16:02:04.981196+07	2026-06-03 16:02:46.202912+07	charge_arrived	mpxu6wytbo8yyamjf8l	A06
1229	6277ff2f	AGV02	go_to	17	completed	2026-06-03 16:01:19.475719+07	2026-06-03 16:01:45.299869+07	2026-06-03 16:02:50.418884+07	event:continue	mpxu795zpmo6tgrc5d	A06
1230	e2c9b822	AGV02	go_charge	\N	completed	2026-06-03 16:01:19.485712+07	2026-06-03 16:02:50.418884+07	2026-06-03 16:02:55.568956+07		mpxu795zpmo6tgrc5d	A06
1232	8908f59b	AGV02	go_charge	\N	completed	2026-06-03 16:02:50.44363+07	2026-06-03 16:02:55.570956+07	2026-06-03 16:03:38.104678+07	charge_arrived	mpxu795zpmo6tgrc5d	A06
1233	a32aefee	AGV01	go_to	18	cancelled	2026-06-03 16:03:06.702798+07	2026-06-03 16:03:06.702798+07	2026-06-03 16:07:25.522954+07	force-cancelled by user	mpxu9k1s0nt2r09uzbk	A06
1234	b201f209	AGV01	go_to	18	cancelled	2026-06-03 16:03:06.720677+07	\N	2026-06-03 16:07:25.52897+07	cancelled by user	mpxu9k1s0nt2r09uzbk	A06
1235	a639f527	AGV01	go_charge	\N	cancelled	2026-06-03 16:03:06.751689+07	\N	2026-06-03 16:07:25.52897+07	cancelled by user	mpxu9k1s0nt2r09uzbk	A06
1239	24749a8f	AGV02	go_to	18	running	2026-06-03 16:10:20.626838+07	\N	\N	\N	mpxuiuvhuryaegqa87l	A06
1240	fb7dde4d	AGV02	go_to	18	queued	2026-06-03 16:10:20.64785+07	\N	\N	\N	mpxuiuvhuryaegqa87l	A06
1241	cb9b56ca	AGV02	go_charge	\N	queued	2026-06-03 16:10:20.665853+07	\N	\N	\N	mpxuiuvhuryaegqa87l	A06
1333	9c7c13a9	AGV02	go_to	17	running	2026-06-03 16:50:19.293307+07	\N	\N	\N	mpxvy9p3hw5ra7vad55	A06
1331	2f2a4adc	AGV01	go_to	17	completed	2026-06-03 16:50:07.289112+07	2026-06-03 16:50:35.242299+07	2026-06-03 16:50:55.396914+07	lifecycle:picking:confirmed	mpxvy06v87841djeqwi	A06
1332	fde7f10d	AGV01	go_charge	\N	completed	2026-06-03 16:50:07.29911+07	2026-06-03 16:50:55.397921+07	2026-06-03 16:51:00.749641+07		mpxvy06v87841djeqwi	A06
1479	53eb854d	AGV01	go_charge	\N	completed	2026-06-04 10:38:18.436781+07	2026-06-04 10:38:27.731636+07	2026-06-04 10:38:27.741661+07	bounce_wait	mpyy22w4bodpj0ya33f	A06
1392	152e2ab9	AGV01	go_to	17	completed	2026-06-04 09:13:16.063767+07	2026-06-04 09:13:46.246072+07	2026-06-04 09:14:04.019944+07	lifecycle:picking:confirmed	mpyv2cf8hb9rpgnvzoh	A06
1393	f7dd13f1	AGV01	go_charge	\N	completed	2026-06-04 09:13:16.081941+07	2026-06-04 09:14:04.019944+07	2026-06-04 09:14:12.302944+07		mpyv2cf8hb9rpgnvzoh	A06
1394	2cb6e8da	AGV02	go_to	17	completed	2026-06-04 09:13:28.647816+07	2026-06-04 09:13:28.647816+07	2026-06-04 09:14:33.869485+07	lifecycle:picking:confirmed	mpyv2m69n6wy18i7q9	A06
1396	a278a4f4	AGV02	go_charge	\N	cancelled	2026-06-04 09:13:29.039152+07	\N	2026-06-04 09:15:12.434188+07	cancelled by user	mpyv2m69n6wy18i7q9	A06
1476	41dc06c7	AGV02	go_to	17	cancelled	2026-06-04 10:37:27.80409+07	2026-06-04 10:37:56.159372+07	2026-06-04 10:47:52.498339+07	force-cancelled by user	mpyy2mednidvd18m759	A06
1465	3cac1594	AGV01	go_charge	\N	completed	2026-06-04 10:32:44.648883+07	2026-06-04 10:33:38.418009+07	2026-06-04 10:33:47.905882+07		mpyxwjrf8xb04kw76s	A06
1478	63b00120	AGV02	go_to	17	cancelled	2026-06-04 10:37:56.161371+07	\N	2026-06-04 10:47:52.498339+07	cancelled by user	mpyy2mednidvd18m759	A06
1469	f9f92eee	AGV01	go_charge	\N	completed	2026-06-04 10:33:38.572079+07	2026-06-04 10:33:47.905882+07	2026-06-04 10:33:47.913883+07	bounce_wait	mpyxwjrf8xb04kw76s	A06
1466	7cb521e4	AGV02	go_to	17	completed	2026-06-04 10:33:10.161054+07	2026-06-04 10:33:10.161054+07	2026-06-04 10:34:04.526824+07	lifecycle:picking:confirmed	mpyxx3m5abt1y3d25u6	A06
1470	d1755e30	AGV01	go_charge	\N	completed	2026-06-04 10:34:14.197706+07	2026-06-04 10:34:14.197706+07	2026-06-04 10:35:02.756823+07	charge_arrived	\N	bounce_retry
1477	98f9dd85	AGV02	go_charge	\N	cancelled	2026-06-04 10:37:27.814583+07	\N	2026-06-04 10:47:52.498339+07	cancelled by user	mpyy2mednidvd18m759	A06
1513	b79bda33	AGV01	go_charge	14	cancelled	2026-06-04 15:54:26.81037+07	\N	2026-06-04 16:01:43.926822+07	cancelled by user	mpz9dr7876snp8u8z8r	Sạc Pin
1582	21282eda	AGV01	go_to	69	completed	2026-06-05 09:15:24.677162+07	2026-06-05 09:15:24.677162+07	2026-06-05 09:15:47.369948+07	lifecycle:picking:confirmed	mq0akydcwef4z9vo7to	A06
1515	bc1d54b0	AGV01	go_to	18	completed	2026-06-04 16:02:11.269615+07	2026-06-04 16:02:41.471468+07	2026-06-04 16:02:49.402782+07		mpz9o7wi7bqkppnera9	A02
1519	7f090056	AGV01	go_to	18	completed	2026-06-04 16:03:08.997286+07	2026-06-04 16:03:17.666842+07	2026-06-04 16:03:36.278685+07	lifecycle:picking:confirmed	mpz9o7wi7bqkppnera9	A02
1667	96676367	AGV02	go_to	17	completed	2026-06-05 09:57:40.922901+07	2026-06-05 10:02:05.758939+07	2026-06-05 10:02:27.65022+07	lifecycle:picking:confirmed	mq0c1cn5xh357t2eg5	A06
1516	c31e889a	AGV01	go_charge	\N	completed	2026-06-04 16:02:11.281239+07	2026-06-04 16:03:36.279679+07	2026-06-04 16:04:07.739158+07	charge_arrived	mpz9o7wi7bqkppnera9	A02
1594	fc3ff27e	AGV02	go_to	17	completed	2026-06-05 09:19:30.972766+07	2026-06-05 09:20:14.376924+07	2026-06-05 09:24:22.066337+07	lifecycle:picking:confirmed	mq0apjp3enamnnn2t8u	A06
1580	a390afc8	AGV02	go_charge	\N	completed	2026-06-05 09:14:27.083288+07	2026-06-05 09:14:47.823609+07	2026-06-05 09:14:47.902429+07	bounce_wait	mq0ai2psanec35p5cqk	A06
1738	7524629c	AGV01	go_to	17	completed	2026-06-05 10:45:35.851914+07	2026-06-05 10:45:35.851914+07	2026-06-05 10:46:10.507505+07	lifecycle:picking:confirmed	mq0dsxnezi4m5q7i4j	A06
1740	5ae4d8c6	AGV01	go_charge	\N	completed	2026-06-05 10:45:36.285696+07	2026-06-05 10:46:32.788526+07	2026-06-05 10:46:51.126677+07		mq0dsxnezi4m5q7i4j	A06
1668	b6e70672	AGV02	go_charge	\N	completed	2026-06-05 10:02:27.870402+07	2026-06-05 10:02:42.545478+07	2026-06-05 10:03:22.479623+07	charge_arrived	mq0c1cn5xh357t2eg5	A06
1741	27198b40	AGV02	go_to	17	completed	2026-06-05 10:45:55.953566+07	2026-06-05 10:45:55.953566+07	2026-06-05 10:46:52.372855+07	lifecycle:picking:confirmed	mq0dtd64t4r1dn2ecug	A06
1739	d177fec8	AGV01	go_to	17	completed	2026-06-05 10:45:36.247045+07	2026-06-05 10:46:10.511519+07	2026-06-05 10:46:32.788526+07	lifecycle:picking:confirmed	mq0dsxnezi4m5q7i4j	A06
1745	f32e2690	AGV01	go_charge	\N	completed	2026-06-05 10:47:03.202456+07	2026-06-05 10:47:03.202456+07	2026-06-05 10:47:57.373764+07	charge_arrived	\N	bounce_retry
2793	de4008ec	AGV01	go_to	8	cancelled	2026-06-15 10:56:27.717825+07	2026-06-15 10:56:27.718152+07	2026-06-15 10:59:16.520704+07	force-cancelled by user	mqeoijy2p8n8127dea	yield_resume
1752	7c81364d	AGV02	go_charge	\N	completed	2026-06-05 10:49:36.349938+07	2026-06-05 10:55:01.980852+07	2026-06-05 10:55:52.319943+07	charge_arrived	mq0dy35pib47yd4352g	A06
2047	8b75cb83	AGV02	go_to	64	completed	2026-06-06 11:45:06.046267+07	2026-06-06 11:45:06.046267+07	2026-06-06 11:45:36.305558+07	event:continue	mq1vdaav5z1ly3e7d5e	A02
2794	5c63d9f6	AGV01	go_to	8	cancelled	2026-06-15 10:56:27.791767+07	\N	2026-06-15 10:59:16.520945+07	cancelled by user	mqeoijy2p8n8127dea	yield_resume
2052	fbfbc276	AGV02	go_to	69	completed	2026-06-06 11:46:16.428238+07	2026-06-06 11:46:35.724371+07	2026-06-06 11:47:30.977303+07	event:continue	mq1vdaav5z1ly3e7d5e	A02
2053	56222d03	AGV02	go_to	64	completed	2026-06-06 11:51:09.348503+07	2026-06-06 11:51:09.348503+07	2026-06-06 11:51:40.293146+07	lifecycle:picking:confirmed	mq1vl2mj60tew6928yo	A02
2054	e7c6074c	AGV02	go_to	16	cancelled	2026-06-06 11:51:09.374232+07	\N	2026-06-06 11:51:58.736373+07	cancelled by user	mq1vl2mj60tew6928yo	A02
2061	82319bba	AGV02	go_to	17	cancelled	2026-06-06 11:51:37.816782+07	\N	2026-06-06 11:51:58.736373+07	cancelled by user	mq1vlol7vvpcpirxoh	A02
2797	38a3613a	AGV02	go_to	5	completed	2026-06-15 10:57:38.010382+07	2026-06-15 10:57:51.847886+07	2026-06-15 10:59:22.342596+07	lifecycle:picking:confirmed	mqeoitsrvggghgun36h	A06
3121	4cf86587	AGV02	go_to	16	completed	2026-06-16 14:04:58.119301+07	2026-06-16 14:06:10.803599+07	2026-06-16 14:07:24.942325+07	lifecycle:picking:confirmed	mqgarobeo6pxyf1spq	A02
2865	ed5661bc	AGV02	go_to	19	completed	2026-06-15 13:30:20.038735+07	2026-06-15 13:30:32.094141+07	2026-06-15 13:30:54.33252+07		mqeu3a834kzk9u5zgw8	A06
3116	c58f3721	AGV01	go_to	17	cancelled	2026-06-16 14:04:45.954265+07	\N	2026-06-16 14:09:29.433686+07	cancelled by user	mqgareo2r995j36a5q	A05
2862	9233d0c9	AGV01	go_charge	\N	completed	2026-06-15 13:30:12.671173+07	2026-06-15 13:31:28.188528+07	2026-06-15 13:31:43.435349+07		mqeu34ayd34lw23ffis	A06
3118	b9ee36f2	AGV01	go_charge	\N	cancelled	2026-06-16 14:04:45.958886+07	\N	2026-06-16 14:09:29.433686+07	cancelled by user	mqgareo2r995j36a5q	A05
2867	1286693a	AGV02	go_charge	\N	completed	2026-06-15 13:30:20.058888+07	2026-06-15 13:33:27.428892+07	2026-06-15 13:33:41.996998+07		mqeu3a834kzk9u5zgw8	A06
2870	acc9943b	AGV02	go_charge	\N	completed	2026-06-15 13:33:27.442651+07	2026-06-15 13:33:41.997485+07	2026-06-15 13:36:27.157415+07	charge_arrived	mqeu3a834kzk9u5zgw8	A06
2936	16401864	AGV02	go_charge	\N	completed	2026-06-16 09:25:07.681171+07	2026-06-16 09:27:43.243737+07	2026-06-16 09:28:46.62097+07	charge_arrived	mqg0rsqmxxb3ku08rpf	A06
2941	69474bdc	AGV01	go_to	19	completed	2026-06-16 09:29:03.449112+07	2026-06-16 09:29:03.449098+07	2026-06-16 09:29:16.795982+07	off_route	mqg0wuo8uy0gmf4ojt	A02
2945	8623316b	AGV01	go_to	19	completed	2026-06-16 09:29:16.794676+07	2026-06-16 09:29:16.796526+07	2026-06-16 09:29:16.798469+07	pickup_already_done	mqg0wuo8uy0gmf4ojt	A02
3131	1795d89b	AGV01	go_charge	14	completed	2026-06-16 14:10:04.98509+07	2026-06-16 14:10:04.986467+07	2026-06-16 14:10:11.799819+07	off_route	mqgaxmv7tvrdzj73j8j	Sạc Pin
2942	04720134	AGV01	go_to	17	completed	2026-06-16 09:29:03.483411+07	2026-06-16 09:31:57.872202+07	2026-06-16 09:32:32.436339+07	lifecycle:picking:confirmed	mqg0wuo8uy0gmf4ojt	A02
2944	baae3eca	AGV01	go_charge	\N	completed	2026-06-16 09:29:03.49012+07	2026-06-16 09:32:32.43658+07	2026-06-16 09:33:35.620553+07		mqg0wuo8uy0gmf4ojt	A02
2985	bf8f4542	AGV02	go_to	19	completed	2026-06-16 10:22:19.405532+07	2026-06-16 10:22:19.405524+07	2026-06-16 10:22:30.375013+07		mqg2tcod8g59if87nv9	A02
2990	f0a75eb3	AGV02	go_to	19	completed	2026-06-16 10:22:30.385676+07	2026-06-16 10:22:53.815803+07	2026-06-16 10:23:13.496821+07	event:continue	mqg2tcod8g59if87nv9	A02
2987	6ad9dc6f	AGV02	go_to	17	completed	2026-06-16 10:22:19.447771+07	2026-06-16 10:23:13.498131+07	2026-06-16 10:23:43.961277+07	event:continue	mqg2tcod8g59if87nv9	A02
2984	19e2724c	AGV01	go_charge	\N	cancelled	2026-06-16 10:22:08.822145+07	\N	2026-06-16 10:28:06.96214+07	cancelled by user	mqg2t4d1jyp0cfcz6p	A02
2995	199ee319	AGV02	go_charge	\N	cancelled	2026-06-16 10:28:18.843075+07	2026-06-16 10:28:18.843063+07	2026-06-16 10:28:30.029088+07	force-cancelled by user	mqg3121pmi2bvptlbdg	Sạc Pin
3237	d0c52843	AGV02	go_to	19	completed	2026-06-16 16:40:56.64567+07	2026-06-16 16:40:56.64567+07	2026-06-16 16:40:56.663312+07	dest_wait	mqggc9el0vuse3cpqro	A05
2999	111abc83	AGV02	go_charge	\N	cancelled	2026-06-16 10:29:02.485802+07	2026-06-16 10:29:16.809234+07	2026-06-16 10:29:54.194404+07	force-cancelled by user	mqg31zpyghra7qdsjl4	Sạc Pin
3003	aada5d8e	AGV01	go_charge	\N	cancelled	2026-06-16 10:30:44.832338+07	2026-06-16 10:30:44.832321+07	2026-06-16 10:31:14.850583+07	force-cancelled by user	mqg346p25cd7x27x4op	Sạc Pin
3065	c4bb7cda	AGV01	go_charge	\N	cancelled	2026-06-16 11:48:50.527182+07	\N	2026-06-16 11:49:06.099852+07	cancelled by user	mqg5wm1pj6kqe50pl8	Sạc Pin
3113	816115f0	AGV01	go_to	64	completed	2026-06-16 14:04:45.671484+07	2026-06-16 14:04:45.671476+07	2026-06-16 14:05:20.726063+07	lifecycle:picking:confirmed	mqgareo2r995j36a5q	A05
3149	5f1bf9b4	AGV01	go_to	96	completed	2026-06-16 14:17:32.590493+07	2026-06-16 14:18:17.554896+07	2026-06-16 14:18:31.511674+07		mqgb53r3i1fjyn17vf	A05
3114	f2cb8a04	AGV01	go_to	96	completed	2026-06-16 14:04:45.94776+07	2026-06-16 14:05:36.651534+07	2026-06-16 14:05:53.916358+07		mqgareo2r995j36a5q	A05
3243	41535e54	AGV02	go_charge	\N	queued	2026-06-16 16:40:56.714756+07	\N	\N	\N	mqggc9el0vuse3cpqro	A05
3244	60dd340a	AGV02	go_to	19	queued	2026-06-16 16:40:59.823162+07	\N	\N	\N	mqggc9el0vuse3cpqro	dest_retry
3238	21814f40	AGV02	go_to	16	completed	2026-06-16 16:40:56.666322+07	2026-06-16 16:40:56.666322+07	2026-06-16 16:44:44.506154+07	lifecycle:picking:confirmed	mqggc9el0vuse3cpqro	A05
3151	86995d4b	AGV01	go_to	96	completed	2026-06-16 14:18:31.528352+07	2026-06-16 14:18:48.547894+07	2026-06-16 14:19:05.932499+07		mqgb53r3i1fjyn17vf	A05
3152	c28ff03d	AGV01	go_to	96	completed	2026-06-16 14:18:48.569412+07	2026-06-16 14:19:05.932857+07	2026-06-16 14:20:36.495259+07	off_route	mqgb53r3i1fjyn17vf	A05
3142	e9f1dc0b	AGV02	go_to	16	completed	2026-06-16 14:15:37.149614+07	2026-06-16 14:18:42.262366+07	2026-06-16 14:20:53.340893+07	lifecycle:picking:confirmed	mqgb5deppduqstpidij	A02
3315	3323de1d	AGV02	go_to	16	completed	2026-06-17 15:24:15.930471+07	2026-06-17 15:26:58.47915+07	2026-06-17 15:28:37.126049+07	lifecycle:picking:confirmed	mqht1i431tvwdr671ixh	A05
3139	51f8f5ef	AGV01	go_to	69	completed	2026-06-16 14:15:24.667777+07	2026-06-16 14:22:47.019666+07	2026-06-16 14:23:00.921967+07		mqgb53r3i1fjyn17vf	A05
3179	7ccab65e	AGV01	go_to	19	completed	2026-06-16 16:04:15.286693+07	2026-06-16 16:04:15.286693+07	2026-06-16 16:04:47.777917+07	lifecycle:picking:confirmed	mqgf12s0v316bse7prh	A02
3245	8503bd48	AGV02	go_to	16	completed	2026-06-16 16:44:44.525969+07	2026-06-16 16:45:00.797175+07	2026-06-16 16:45:15.043998+07		mqggc9el0vuse3cpqro	A05
3180	5d525f48	AGV01	go_to	16	completed	2026-06-16 16:04:15.481483+07	2026-06-16 16:05:04.337208+07	2026-06-16 16:05:43.85569+07	lifecycle:picking:confirmed	mqgf12s0v316bse7prh	A02
3185	4f9e1fb0	AGV02	go_to	17	completed	2026-06-16 16:04:29.24973+07	2026-06-16 16:05:21.656572+07	2026-06-16 16:05:48.65728+07	lifecycle:picking:confirmed	mqgf1dkeaiwatba55uo	A02
3249	17c2cb1d	AGV02	go_to	18	running	2026-06-16 16:46:14.47794+07	2026-06-16 16:46:28.664951+07	\N		mqggc9el0vuse3cpqro	A05
3309	a4dbf28f	AGV01	go_to	18	completed	2026-06-17 15:23:53.506958+07	2026-06-17 15:26:54.752726+07	2026-06-17 15:28:40.45483+07	lifecycle:picking:confirmed	mqht10otruzwoswgsvq	A05
3313	5e1c7cc1	AGV02	go_to	15	completed	2026-06-17 15:24:15.926565+07	2026-06-17 15:25:00.582349+07	2026-06-17 15:25:37.632118+07	lifecycle:picking:confirmed	mqht1i431tvwdr671ixh	A05
3319	8715d09c	AGV01	go_to	15	completed	2026-06-17 15:25:14.537125+07	2026-06-17 15:25:30.157013+07	2026-06-17 15:25:52.71254+07		mqht10otruzwoswgsvq	A05
3356	6e580ba9	AGV01	go_charge	\N	cancelled	2026-06-17 15:52:32.92351+07	2026-06-17 15:52:32.92351+07	2026-06-17 15:52:49.985126+07	force-cancelled by user	mqhu1vl8udxp73ty7q	Sạc Pin
3317	3c775b22	AGV02	go_charge	\N	cancelled	2026-06-17 15:24:15.933561+07	2026-06-17 15:30:08.420337+07	2026-06-17 15:36:50.405921+07	force-cancelled by user	mqht1i431tvwdr671ixh	A05
3415	0be258ce	AGV02	go_to	19	completed	2026-06-18 08:13:16.175713+07	2026-06-18 08:13:16.175713+07	2026-06-18 08:13:38.269019+07		mqit33af6cot1unb2zx	A05
3416	ddddcf1e	AGV02	go_to	19	completed	2026-06-18 08:13:16.184781+07	2026-06-18 08:13:38.271315+07	2026-06-18 08:13:59.299928+07	lifecycle:picking:confirmed	mqit33af6cot1unb2zx	A05
3411	b2c4935b	AGV01	go_to	18	completed	2026-06-18 08:12:38.388016+07	2026-06-18 08:14:10.916356+07	2026-06-18 08:14:26.100652+07		mqit2a1jo8v278sc1x	A05
3418	7e257c39	AGV02	go_to	15	completed	2026-06-18 08:13:16.214526+07	2026-06-18 08:14:31.640742+07	2026-06-18 08:14:46.997779+07		mqit33af6cot1unb2zx	A05
3419	3e770a0e	AGV02	go_to	18	cancelled	2026-06-18 08:13:16.228334+07	\N	2026-06-18 08:40:06.864424+07	cancelled by user	mqit33af6cot1unb2zx	A05
3423	2b500e14	AGV01	go_to	18	cancelled	2026-06-18 08:14:26.180048+07	2026-06-18 08:14:47.402148+07	2026-06-18 08:40:12.397764+07	force-cancelled by user	mqit2a1jo8v278sc1x	A05
2049	0b15d5d0	AGV02	go_to	18	completed	2026-06-06 11:45:06.088196+07	2026-06-06 11:45:55.723407+07	2026-06-06 11:46:16.399865+07	event:continue	mq1vdaav5z1ly3e7d5e	A02
2058	a08726c1	AGV02	go_to	64	cancelled	2026-06-06 11:51:37.812268+07	\N	2026-06-06 11:51:47.145309+07	cancelled by user	mq1vlol7vvpcpirxoh	A02
2055	360b73c1	AGV02	go_to	19	cancelled	2026-06-06 11:51:09.373219+07	2026-06-06 11:51:40.293146+07	2026-06-06 11:51:58.73534+07	force-cancelled by user	mq1vl2mj60tew6928yo	A02
2056	928c21b0	AGV02	go_to	96	cancelled	2026-06-06 11:51:09.375734+07	\N	2026-06-06 11:51:58.736373+07	cancelled by user	mq1vl2mj60tew6928yo	A02
2057	0a38662a	AGV02	go_charge	\N	cancelled	2026-06-06 11:51:09.376746+07	\N	2026-06-06 11:51:58.736373+07	cancelled by user	mq1vl2mj60tew6928yo	A02
2059	e1f665b2	AGV02	go_to	19	cancelled	2026-06-06 11:51:37.815267+07	\N	2026-06-06 11:51:58.736373+07	cancelled by user	mq1vlol7vvpcpirxoh	A02
2062	0c1a5b0f	AGV02	go_charge	\N	cancelled	2026-06-06 11:51:37.817787+07	\N	2026-06-06 11:51:58.736373+07	cancelled by user	mq1vlol7vvpcpirxoh	A02
2792	48991c46	AGV01	go_charge	\N	cancelled	2026-06-15 10:56:13.2994+07	\N	2026-06-15 10:59:16.520945+07	cancelled by user	mqeoijy2p8n8127dea	yield_resume
2795	38063d3d	AGV02	go_charge	\N	completed	2026-06-15 10:57:27.884072+07	2026-06-15 10:59:22.342665+07	2026-06-15 11:00:08.814417+07	charge_arrived	mqeoitsrvggghgun36h	A06
2799	aa27ad9f	AGV01	go_charge	\N	cancelled	2026-06-15 10:59:36.160898+07	\N	2026-06-15 11:01:41.055649+07	cancelled by user	mqeopfx5b3wss8vf0x9	Sạc Pin
2800	16bcbf7e	AGV01	go_charge	\N	cancelled	2026-06-15 11:02:10.387056+07	2026-06-15 11:02:10.387032+07	2026-06-15 11:02:32.079675+07	force-cancelled by user	mqeosqxtkafw3qte3vl	Sạc Pin
3084	72fdc288	AGV01	go_to	9	completed	2026-06-16 11:58:58.93116+07	2026-06-16 11:58:58.934161+07	2026-06-16 11:59:14.058656+07	off_route	mqg643a9yx8rzeckwg7	A05
2802	828ae63d	AGV01	go_charge	\N	completed	2026-06-15 11:02:37.036652+07	2026-06-15 11:02:53.260861+07	2026-06-15 11:03:38.915002+07	charge_arrived	mqeotbh79fgg9bybq6	Sạc Pin
2864	673104d1	AGV02	go_to	19	completed	2026-06-15 13:30:20.032028+07	2026-06-15 13:30:20.032019+07	2026-06-15 13:30:32.092677+07		mqeu3a834kzk9u5zgw8	A06
3074	4f086809	AGV02	go_to	17	completed	2026-06-16 11:54:49.565304+07	2026-06-16 11:59:00.492093+07	2026-06-16 11:59:28.255866+07	event:continue	mqg64b5om3fq6munei	A02
2863	c0783dce	AGV01	go_to	17	completed	2026-06-15 13:30:12.670296+07	2026-06-15 13:30:45.261693+07	2026-06-15 13:31:28.188258+07	lifecycle:picking:confirmed	mqeu34ayd34lw23ffis	A06
3086	58699167	AGV01	go_to	15	completed	2026-06-16 11:59:14.057311+07	2026-06-16 11:59:14.059647+07	2026-06-16 11:59:33.624216+07		mqg643a9yx8rzeckwg7	A05
2866	fda2db08	AGV02	go_to	17	completed	2026-06-15 13:30:20.057379+07	2026-06-15 13:31:35.891794+07	2026-06-15 13:33:27.428813+07	lifecycle:picking:confirmed	mqeu3a834kzk9u5zgw8	A06
2869	4694addc	AGV01	go_charge	\N	cancelled	2026-06-15 13:31:28.210255+07	2026-06-15 13:31:43.43655+07	2026-06-15 13:34:34.342867+07	force-cancelled by user	mqeu34ayd34lw23ffis	A06
2946	ae1817c1	AGV02	go_to	19	completed	2026-06-16 09:29:19.82767+07	2026-06-16 09:29:19.827664+07	2026-06-16 09:30:06.952577+07	lifecycle:picking:confirmed	mqg0x7b92ot2vi46f33	A02
3083	d5d4c502	AGV01	go_to	9	cancelled	2026-06-16 11:58:43.023719+07	\N	2026-06-16 13:11:26.29116+07	cancelled by user	mqg643a9yx8rzeckwg7	A05
2948	8ad5cec7	AGV02	go_to	18	completed	2026-06-16 09:29:19.851298+07	2026-06-16 09:30:47.466024+07	2026-06-16 09:31:01.13468+07		mqg0x7b92ot2vi46f33	A02
2943	c1ba000d	AGV01	go_to	15	completed	2026-06-16 09:29:03.480622+07	2026-06-16 09:29:16.799599+07	2026-06-16 09:31:57.872122+07	lifecycle:picking:confirmed	mqg0wuo8uy0gmf4ojt	A02
2949	21576e7c	AGV02	go_charge	\N	cancelled	2026-06-16 09:29:19.856134+07	\N	2026-06-16 09:33:01.14082+07	cancelled by user	mqg0x7b92ot2vi46f33	A02
2952	3c1a742c	AGV02	go_charge	\N	cancelled	2026-06-16 09:33:06.477762+07	2026-06-16 09:33:06.477757+07	2026-06-16 09:33:18.340178+07	force-cancelled by user	mqg1227y8xvni9nmcbf	Sạc Pin
2998	8b76c54c	AGV02	go_charge	\N	completed	2026-06-16 10:29:02.477172+07	2026-06-16 10:29:02.477166+07	2026-06-16 10:29:16.808816+07		mqg31zpyghra7qdsjl4	Sạc Pin
3069	81ea3aed	AGV01	go_to	16	cancelled	2026-06-16 11:54:39.370194+07	\N	2026-06-16 13:11:26.29116+07	cancelled by user	mqg643a9yx8rzeckwg7	A05
3002	679d915c	AGV02	go_charge	\N	completed	2026-06-16 10:30:19.440951+07	2026-06-16 10:30:33.841763+07	2026-06-16 10:31:09.887999+07	charge_arrived	mqg33n2w5qw1kig567v	Sạc Pin
3066	02b30b7e	AGV01	go_to	64	completed	2026-06-16 11:54:39.313049+07	2026-06-16 11:54:39.313028+07	2026-06-16 11:55:24.555427+07	lifecycle:picking:confirmed	mqg643a9yx8rzeckwg7	A05
3071	e884acfb	AGV01	go_charge	\N	cancelled	2026-06-16 11:54:39.376575+07	\N	2026-06-16 13:11:26.29116+07	cancelled by user	mqg643a9yx8rzeckwg7	A05
3067	f33c3049	AGV01	go_to	96	completed	2026-06-16 11:54:39.361777+07	2026-06-16 11:55:42.296971+07	2026-06-16 11:55:54.333223+07		mqg643a9yx8rzeckwg7	A05
3076	c0101420	AGV02	go_charge	\N	cancelled	2026-06-16 11:54:49.569835+07	\N	2026-06-16 13:11:30.364088+07	cancelled by user	mqg64b5om3fq6munei	A02
3078	ec74d0f9	AGV01	go_to	96	completed	2026-06-16 11:55:54.352412+07	2026-06-16 11:56:13.521211+07	2026-06-16 11:56:29.682246+07	off_route	mqg643a9yx8rzeckwg7	A05
3088	baf197a3	AGV02	go_to	15	cancelled	2026-06-16 11:59:28.297847+07	2026-06-16 11:59:43.024808+07	2026-06-16 13:11:30.363939+07	force-cancelled by user	mqg64b5om3fq6munei	A02
3115	0088be21	AGV01	go_to	19	completed	2026-06-16 14:04:45.946473+07	2026-06-16 14:05:20.726217+07	2026-06-16 14:05:36.65111+07	lifecycle:picking:confirmed	mqgareo2r995j36a5q	A05
3250	fdc97ebb	AGV01	go_to	19	completed	2026-06-17 14:25:57.141369+07	2026-06-17 14:25:57.141369+07	2026-06-17 14:26:31.155314+07	lifecycle:picking:confirmed	mqhqyibpsjmtqtixyk	A05
3253	71664ced	AGV01	go_to	15	completed	2026-06-17 14:25:57.195581+07	2026-06-17 14:27:42.244899+07	2026-06-17 14:28:01.491324+07		mqhqyibpsjmtqtixyk	A05
3128	250be8ff	AGV02	go_to	18	completed	2026-06-16 14:07:24.969124+07	2026-06-16 14:07:42.85996+07	2026-06-16 14:08:11.190279+07	lifecycle:picking:confirmed	mqgarobeo6pxyf1spq	A02
3123	722befe8	AGV02	go_charge	\N	completed	2026-06-16 14:04:58.122781+07	2026-06-16 14:08:11.190388+07	2026-06-16 14:08:51.353708+07	charge_arrived	mqgarobeo6pxyf1spq	A02
3125	7e957ecd	AGV01	go_to	96	cancelled	2026-06-16 14:05:53.936554+07	\N	2026-06-16 14:09:29.433686+07	cancelled by user	mqgareo2r995j36a5q	A05
3117	c336bf60	AGV01	go_to	15	cancelled	2026-06-16 14:04:45.955757+07	\N	2026-06-16 14:09:29.433686+07	cancelled by user	mqgareo2r995j36a5q	A05
3181	bd43b931	AGV01	go_to	18	completed	2026-06-16 16:04:15.479966+07	2026-06-16 16:04:47.777917+07	2026-06-16 16:05:04.337208+07	lifecycle:picking:confirmed	mqgf12s0v316bse7prh	A02
3184	5757d075	AGV02	go_to	19	completed	2026-06-16 16:04:29.21774+07	2026-06-16 16:04:57.805541+07	2026-06-16 16:05:21.655586+07	lifecycle:picking:confirmed	mqgf1dkeaiwatba55uo	A02
3251	b04e4604	AGV01	go_to	18	completed	2026-06-17 14:25:57.18908+07	2026-06-17 14:26:31.156324+07	2026-06-17 14:26:58.072383+07	event:continue	mqhqyibpsjmtqtixyk	A05
3186	5f683a91	AGV02	go_to	15	completed	2026-06-16 16:04:29.250727+07	2026-06-16 16:05:48.65728+07	2026-06-16 16:06:03.213024+07		mqgf1dkeaiwatba55uo	A02
3189	7f42f04e	AGV02	go_to	15	completed	2026-06-16 16:05:48.684963+07	2026-06-16 16:06:03.21402+07	2026-06-16 16:06:54.841231+07	lifecycle:picking:confirmed	mqgf1dkeaiwatba55uo	A02
3262	70df0aa4	AGV02	go_charge	\N	cancelled	2026-06-17 14:26:19.347109+07	\N	2026-06-17 14:37:55.150819+07	cancelled by user	mqhqyzkaa3unckw0oin	A05
3267	4d388634	AGV01	go_to	17	completed	2026-06-17 14:28:15.453437+07	2026-06-17 14:28:30.436071+07	2026-06-17 14:29:14.387366+07	event:continue	mqhqyibpsjmtqtixyk	A05
3265	2716f73f	AGV02	go_to	16	completed	2026-06-17 14:27:34.969315+07	2026-06-17 14:27:51.607239+07	2026-06-17 14:28:49.2537+07	event:continue	mqhqyzkaa3unckw0oin	A05
3268	2ef788b4	AGV02	go_to	18	completed	2026-06-17 14:28:49.317976+07	2026-06-17 14:29:03.907888+07	2026-06-17 14:29:41.894946+07	event:continue	mqhqyzkaa3unckw0oin	A05
3311	b2cecf8c	AGV02	go_to	19	completed	2026-06-17 15:24:15.893255+07	2026-06-17 15:24:15.893255+07	2026-06-17 15:24:18.184449+07		mqht1i431tvwdr671ixh	A05
3310	dc67961c	AGV01	go_to	16	completed	2026-06-17 15:23:53.509961+07	2026-06-17 15:28:40.45483+07	2026-06-17 15:29:38.426251+07	lifecycle:picking:confirmed	mqht10otruzwoswgsvq	A05
3312	4c1ce63d	AGV02	go_to	19	completed	2026-06-17 15:24:15.902574+07	2026-06-17 15:24:18.185614+07	2026-06-17 15:24:37.908107+07		mqht1i431tvwdr671ixh	A05
3314	24719249	AGV02	go_to	17	completed	2026-06-17 15:24:15.927562+07	2026-06-17 15:25:37.632118+07	2026-06-17 15:26:58.47915+07	lifecycle:picking:confirmed	mqht1i431tvwdr671ixh	A05
3323	33ce0260	AGV01	go_to	15	completed	2026-06-17 15:26:16.31839+07	2026-06-17 15:26:34.045738+07	2026-06-17 15:26:54.752726+07	lifecycle:picking:confirmed	mqht10otruzwoswgsvq	A05
3316	1f077fe2	AGV02	go_to	18	completed	2026-06-17 15:24:15.931487+07	2026-06-17 15:28:37.126049+07	2026-06-17 15:28:49.740475+07		mqht1i431tvwdr671ixh	A05
2060	371ca872	AGV02	go_to	96	cancelled	2026-06-06 11:51:37.815772+07	\N	2026-06-06 11:51:58.736373+07	cancelled by user	mq1vlol7vvpcpirxoh	A02
2063	346c4f93	AGV02	go_charge	\N	completed	2026-06-06 11:52:08.176717+07	2026-06-06 11:52:08.176717+07	2026-06-06 11:52:19.639057+07		mq1vmc1fz0k6nc3hr8r	Sạc Pin
2079	889e1702	AGV01	go_to	96	cancelled	2026-06-06 11:57:15.254153+07	2026-06-06 11:58:25.501106+07	2026-06-06 11:58:59.759935+07	force-cancelled by user	mq1vnu4p325e7jmg7nd	A02
2064	0f04aa19	AGV02	go_charge	\N	completed	2026-06-06 11:52:08.251867+07	2026-06-06 11:52:19.643062+07	2026-06-06 11:52:49.358637+07	charge_arrived	mq1vmc1fz0k6nc3hr8r	Sạc Pin
2069	849ec9cd	AGV01	go_charge	\N	cancelled	2026-06-06 11:53:18.330466+07	\N	2026-06-06 11:58:59.762939+07	cancelled by user	mq1vnu4p325e7jmg7nd	A02
2065	f4f23348	AGV01	go_to	64	completed	2026-06-06 11:53:18.295467+07	2026-06-06 11:53:18.295467+07	2026-06-06 11:53:53.747386+07	lifecycle:picking:confirmed	mq1vnu4p325e7jmg7nd	A02
2085	799c678b	AGV01	go_to	96	cancelled	2026-06-06 11:58:25.534189+07	\N	2026-06-06 11:58:59.762939+07	cancelled by user	mq1vnu4p325e7jmg7nd	A02
2066	4b9b1d21	AGV01	go_to	19	completed	2026-06-06 11:53:18.325467+07	2026-06-06 11:53:53.747386+07	2026-06-06 11:54:07.525009+07	lifecycle:picking:confirmed	mq1vnu4p325e7jmg7nd	A02
2070	03453b4b	AGV02	go_to	64	completed	2026-06-06 11:54:16.887714+07	2026-06-06 11:54:16.887714+07	2026-06-06 11:54:45.620075+07	lifecycle:picking:confirmed	mq1vp3bw51nixc48blf	A02
2067	13d9fc89	AGV01	go_to	16	completed	2026-06-06 11:53:18.326474+07	2026-06-06 11:54:07.525009+07	2026-06-06 11:54:57.321317+07	lifecycle:picking:confirmed	mq1vnu4p325e7jmg7nd	A02
2071	886d176f	AGV02	go_to	19	completed	2026-06-06 11:54:16.903786+07	2026-06-06 11:54:45.620075+07	2026-06-06 11:54:59.495032+07	lifecycle:picking:confirmed	mq1vp3bw51nixc48blf	A02
2086	03cb21c8	AGV01	go_charge	\N	completed	2026-06-06 11:59:04.948015+07	2026-06-06 11:59:04.947009+07	2026-06-06 11:59:11.65435+07	off_route	mq1vv9mlj7wcnzbvn3n	Sạc Pin
2068	e46ed777	AGV01	go_to	96	completed	2026-06-06 11:53:18.328473+07	2026-06-06 11:54:57.328316+07	2026-06-06 11:55:13.469679+07	off_route	mq1vnu4p325e7jmg7nd	A02
2072	bea1e9fa	AGV02	go_to	17	completed	2026-06-06 11:54:16.905122+07	2026-06-06 11:54:59.495032+07	2026-06-06 11:55:21.219923+07	lifecycle:picking:confirmed	mq1vp3bw51nixc48blf	A02
2076	3f0cbab9	AGV01	go_to	8	completed	2026-06-06 11:55:13.468681+07	2026-06-06 11:55:13.469679+07	2026-06-06 11:55:28.756258+07		mq1vnu4p325e7jmg7nd	A02
2087	14a1be2b	AGV01	go_charge	14	completed	2026-06-06 11:59:11.652359+07	2026-06-06 11:59:11.655359+07	2026-06-06 11:59:26.350858+07		mq1vv9mlj7wcnzbvn3n	Sạc Pin
2073	c12da101	AGV02	go_to	69	completed	2026-06-06 11:54:16.909473+07	2026-06-06 11:55:21.219923+07	2026-06-06 11:55:36.065349+07		mq1vp3bw51nixc48blf	A02
2097	68d4c2db	AGV02	go_to	69	completed	2026-06-06 14:22:59.859608+07	2026-06-06 14:24:05.719842+07	2026-06-06 14:24:20.621042+07		mq210cbbvz3rt7gp94c	A02
2078	4bf18d69	AGV02	go_to	69	completed	2026-06-06 11:55:21.244927+07	2026-06-06 11:55:36.065349+07	2026-06-06 11:56:31.133472+07	lifecycle:picking:confirmed	mq1vp3bw51nixc48blf	A02
2088	56907513	AGV01	go_charge	\N	completed	2026-06-06 11:59:11.710271+07	2026-06-06 11:59:26.352965+07	2026-06-06 12:00:11.431935+07	charge_arrived	mq1vv9mlj7wcnzbvn3n	Sạc Pin
2077	e5477a81	AGV01	go_to	8	completed	2026-06-06 11:55:13.511675+07	2026-06-06 11:55:28.757204+07	2026-06-06 11:56:48.716989+07	lifecycle:picking:confirmed	mq1vnu4p325e7jmg7nd	A02
2074	7848bb62	AGV02	go_charge	\N	completed	2026-06-06 11:54:16.911485+07	2026-06-06 11:56:31.133472+07	2026-06-06 11:57:15.859346+07	charge_arrived	mq1vp3bw51nixc48blf	A02
2075	dc0ef6a9	AGV01	go_to	96	completed	2026-06-06 11:54:57.361317+07	2026-06-06 11:56:48.716989+07	2026-06-06 11:57:26.391354+07	off_route	mq1vnu4p325e7jmg7nd	A02
2080	6fe1e422	AGV01	go_to	5	completed	2026-06-06 11:57:26.38935+07	2026-06-06 11:57:26.391354+07	2026-06-06 11:57:39.598731+07	off_route	mq1vnu4p325e7jmg7nd	A02
2082	c1642122	AGV01	go_to	4	completed	2026-06-06 11:57:39.59273+07	2026-06-06 11:57:39.624742+07	2026-06-06 11:57:56.20216+07	off_route	mq1vnu4p325e7jmg7nd	A02
2084	45f12096	AGV01	go_to	19	completed	2026-06-06 11:57:56.20216+07	2026-06-06 11:57:56.203159+07	2026-06-06 11:57:56.205136+07	pickup_already_done	mq1vnu4p325e7jmg7nd	A02
2083	8af2b168	AGV01	go_to	4	completed	2026-06-06 11:57:39.782954+07	2026-06-06 11:57:56.208044+07	2026-06-06 11:58:14.123377+07	lifecycle:picking:confirmed	mq1vnu4p325e7jmg7nd	A02
2090	5b1f9038	AGV01	go_to	17	cancelled	2026-06-06 14:22:22.083768+07	\N	2026-06-06 14:22:38.45418+07	cancelled by user	mq20ziyqdocf9yycid	A02
2100	bedeea52	AGV01	go_to	19	completed	2026-06-06 14:28:10.697697+07	2026-06-06 14:28:10.697697+07	2026-06-06 14:29:11.67776+07	lifecycle:picking:confirmed	mq21705i0b2pcrgeoxvd	A06
2081	35121043	AGV01	go_to	5	completed	2026-06-06 11:57:26.43138+07	2026-06-06 11:58:14.123377+07	2026-06-06 11:58:25.501106+07	lifecycle:picking:confirmed	mq1vnu4p325e7jmg7nd	A02
2089	a0ad3f63	AGV01	go_to	64	cancelled	2026-06-06 14:22:21.812406+07	2026-06-06 14:22:21.812406+07	2026-06-06 14:22:38.45318+07	force-cancelled by user	mq20ziyqdocf9yycid	A02
2091	52e9ff49	AGV01	go_to	19	cancelled	2026-06-06 14:22:22.080204+07	\N	2026-06-06 14:22:38.45418+07	cancelled by user	mq20ziyqdocf9yycid	A02
2092	73c99996	AGV01	go_to	69	cancelled	2026-06-06 14:22:22.087315+07	\N	2026-06-06 14:22:38.45418+07	cancelled by user	mq20ziyqdocf9yycid	A02
2093	08a23fea	AGV01	go_charge	\N	cancelled	2026-06-06 14:22:22.096325+07	\N	2026-06-06 14:22:38.45418+07	cancelled by user	mq20ziyqdocf9yycid	A02
2101	13b58903	AGV01	go_charge	\N	completed	2026-06-06 14:28:10.748923+07	2026-06-06 14:29:43.540861+07	2026-06-06 14:29:59.276385+07		mq21705i0b2pcrgeoxvd	A06
2094	747c5c5c	AGV02	go_to	64	completed	2026-06-06 14:22:59.817063+07	2026-06-06 14:22:59.817063+07	2026-06-06 14:23:31.414755+07	lifecycle:picking:confirmed	mq210cbbvz3rt7gp94c	A02
2099	4a55c483	AGV02	go_to	69	completed	2026-06-06 14:24:05.74085+07	2026-06-06 14:24:20.621042+07	2026-06-06 14:25:15.808262+07	lifecycle:picking:confirmed	mq210cbbvz3rt7gp94c	A02
2095	33761e9b	AGV02	go_to	19	completed	2026-06-06 14:22:59.856597+07	2026-06-06 14:23:31.414755+07	2026-06-06 14:23:45.491293+07	lifecycle:picking:confirmed	mq210cbbvz3rt7gp94c	A02
2096	4b96a97d	AGV02	go_to	17	completed	2026-06-06 14:22:59.857602+07	2026-06-06 14:23:45.491293+07	2026-06-06 14:24:05.719842+07	lifecycle:picking:confirmed	mq210cbbvz3rt7gp94c	A02
2102	aab10b1a	AGV01	go_to	17	completed	2026-06-06 14:28:10.746939+07	2026-06-06 14:29:11.67776+07	2026-06-06 14:29:43.539862+07	lifecycle:picking:confirmed	mq21705i0b2pcrgeoxvd	A06
2098	162dd846	AGV02	go_charge	\N	completed	2026-06-06 14:22:59.8636+07	2026-06-06 14:25:15.817257+07	2026-06-06 14:25:59.399884+07	charge_arrived	mq210cbbvz3rt7gp94c	A02
2103	f6c9c1ed	AGV02	go_to	19	cancelled	2026-06-06 14:28:23.438825+07	2026-06-06 14:28:23.438825+07	2026-06-06 14:28:34.500013+07	force-cancelled by user	mq217a0ooqnit7garyq	A06
2105	960376e3	AGV02	go_to	17	cancelled	2026-06-06 14:28:23.619864+07	\N	2026-06-06 14:28:34.500013+07	cancelled by user	mq217a0ooqnit7garyq	A06
2104	7886c17a	AGV02	go_to	19	cancelled	2026-06-06 14:28:23.446812+07	\N	2026-06-06 14:28:34.500013+07	cancelled by user	mq217a0ooqnit7garyq	A06
2106	8d7480a6	AGV02	go_charge	\N	cancelled	2026-06-06 14:28:23.620862+07	\N	2026-06-06 14:28:34.500013+07	cancelled by user	mq217a0ooqnit7garyq	A06
2109	fb520cc0	AGV02	go_to	17	cancelled	2026-06-06 14:29:03.690385+07	\N	2026-06-06 14:30:56.722356+07	cancelled by user	mq2185156mv89blmo4a	A06
2112	f710a028	AGV01	go_charge	\N	completed	2026-06-06 14:32:10.132393+07	2026-06-06 14:32:10.132393+07	2026-06-06 14:32:20.196532+07	off_route	mq21c4xzwiod94wq6b	Sạc Pin
2107	1b6b29e5	AGV02	go_to	19	cancelled	2026-06-06 14:29:03.639145+07	2026-06-06 14:29:03.639145+07	2026-06-06 14:30:56.722356+07	force-cancelled by user	mq2185156mv89blmo4a	A06
2108	fd462a94	AGV02	go_to	19	cancelled	2026-06-06 14:29:03.646216+07	\N	2026-06-06 14:30:56.722356+07	cancelled by user	mq2185156mv89blmo4a	A06
2110	4ee97d3a	AGV02	go_charge	\N	cancelled	2026-06-06 14:29:03.693408+07	\N	2026-06-06 14:30:56.722356+07	cancelled by user	mq2185156mv89blmo4a	A06
2111	f9a58a3f	AGV01	go_charge	\N	cancelled	2026-06-06 14:29:43.558374+07	2026-06-06 14:29:59.276385+07	2026-06-06 14:31:59.193952+07	force-cancelled by user	mq21705i0b2pcrgeoxvd	A06
2115	cc23d2d0	AGV01	go_to	19	cancelled	2026-06-06 14:52:03.274098+07	2026-06-06 14:52:03.274098+07	2026-06-06 14:53:03.685831+07	force-cancelled by user	mq221pjmis0gmne1x3e	A06
2113	5767f609	AGV01	go_charge	14	completed	2026-06-06 14:32:20.195542+07	2026-06-06 14:32:20.199437+07	2026-06-06 14:32:38.129185+07		mq21c4xzwiod94wq6b	Sạc Pin
2114	9874f11a	AGV01	go_charge	\N	completed	2026-06-06 14:32:20.24445+07	2026-06-06 14:32:38.130186+07	2026-06-06 14:33:12.24242+07	charge_arrived	mq21c4xzwiod94wq6b	Sạc Pin
2116	6c25fd2d	AGV01	go_charge	\N	cancelled	2026-06-06 14:52:03.579419+07	\N	2026-06-06 14:53:03.706861+07	cancelled by user	mq221pjmis0gmne1x3e	A06
2117	8dfb3619	AGV01	go_to	17	cancelled	2026-06-06 14:52:03.578412+07	\N	2026-06-06 14:53:03.706861+07	cancelled by user	mq221pjmis0gmne1x3e	A06
2118	dae99eab	AGV01	go_to	19	running	2026-06-06 14:53:33.561776+07	\N	\N	\N	mq223n7cbmstasgj0fl	A06
2119	9d76af7b	AGV01	go_charge	\N	queued	2026-06-06 14:53:33.667333+07	\N	\N	\N	mq223n7cbmstasgj0fl	A06
2120	a4e6968d	AGV01	go_to	17	queued	2026-06-06 14:53:33.666319+07	\N	\N	\N	mq223n7cbmstasgj0fl	A06
2155	0b2a7992	AGV02	go_charge	\N	completed	2026-06-08 09:39:14.212606+07	2026-06-08 09:44:33.6508+07	2026-06-08 09:44:48.971821+07		mq4lr4lbl3a96pfed	A06
2121	2af88702	AGV01	go_to	19	completed	2026-06-06 15:09:09.409188+07	2026-06-06 15:09:09.409188+07	2026-06-06 15:10:29.98114+07	lifecycle:picking:confirmed	mq22npchph7ck1bfnp	A06
2125	99820223	AGV02	go_to	19	cancelled	2026-06-06 15:09:24.917785+07	\N	2026-06-06 15:10:49.643933+07	cancelled by user	mq22o1apywm1kbo336	A06
2126	b675ac04	AGV02	go_to	17	cancelled	2026-06-06 15:09:24.935533+07	\N	2026-06-06 15:10:49.643933+07	cancelled by user	mq22o1apywm1kbo336	A06
2124	163ba4d4	AGV02	go_to	19	cancelled	2026-06-06 15:09:24.907678+07	2026-06-06 15:09:24.907678+07	2026-06-06 15:10:49.643933+07	force-cancelled by user	mq22o1apywm1kbo336	A06
2127	544676bd	AGV02	go_charge	\N	cancelled	2026-06-06 15:09:24.936536+07	\N	2026-06-06 15:10:49.643933+07	cancelled by user	mq22o1apywm1kbo336	A06
2122	b9c0e565	AGV01	go_to	17	completed	2026-06-06 15:09:09.740602+07	2026-06-06 15:10:29.986232+07	2026-06-06 15:11:09.653286+07	lifecycle:picking:confirmed	mq22npchph7ck1bfnp	A06
2165	c8fe7709	AGV02	go_to	19	completed	2026-06-08 10:57:34.184954+07	2026-06-08 10:57:34.184954+07	2026-06-08 10:57:53.919061+07		mq4ojv46ifejuq6wmi	A06
2123	f57d4124	AGV01	go_charge	\N	completed	2026-06-06 15:09:09.742598+07	2026-06-06 15:11:09.653286+07	2026-06-06 15:11:25.400681+07		mq22npchph7ck1bfnp	A06
2152	6cb2b687	AGV02	go_to	19	completed	2026-06-08 09:39:14.181084+07	2026-06-08 09:39:14.181084+07	2026-06-08 09:39:40.24482+07		mq4lr4lbl3a96pfed	A06
2128	46c719a0	AGV01	go_charge	\N	completed	2026-06-06 15:11:09.67129+07	2026-06-06 15:11:25.401692+07	2026-06-06 15:12:23.247615+07	charge_arrived	mq22npchph7ck1bfnp	A06
2134	743476e5	AGV02	go_to	17	queued	2026-06-06 15:14:50.010267+07	\N	\N	\N	mq22v05tjey4g7sdvk	A06
2135	7d1263a9	AGV02	go_charge	\N	queued	2026-06-06 15:14:50.012289+07	\N	\N	\N	mq22v05tjey4g7sdvk	A06
2132	193a2271	AGV02	go_to	19	completed	2026-06-06 15:14:49.987665+07	2026-06-06 15:14:49.987665+07	2026-06-06 15:15:03.42855+07		mq22v05tjey4g7sdvk	A06
2150	1ddb080b	AGV01	go_to	17	completed	2026-06-08 09:38:55.085558+07	2026-06-08 09:39:30.029054+07	2026-06-08 09:40:08.69004+07	lifecycle:picking:confirmed	mq4lqpsrtxq6iulozub	A06
2136	0b4bee67	AGV02	go_to	19	queued	2026-06-06 15:15:03.811806+07	\N	\N	\N	mq22v05tjey4g7sdvk	A06
2157	4d57e466	AGV01	go_to	6	completed	2026-06-08 09:40:25.764558+07	2026-06-08 09:40:25.766551+07	2026-06-08 09:45:22.114879+07	lifecycle:picking:confirmed	mq4lqpsrtxq6iulozub	A06
2129	5eb115b9	AGV01	go_to	19	completed	2026-06-06 15:14:33.534358+07	2026-06-06 15:14:33.534358+07	2026-06-06 15:15:07.584157+07	lifecycle:picking:confirmed	mq22unfg1pp32z2m33o	A06
2133	1c0f2ffc	AGV02	go_to	19	completed	2026-06-06 15:14:49.994663+07	2026-06-06 15:15:03.430548+07	2026-06-06 15:15:26.674801+07	off_route	mq22v05tjey4g7sdvk	A06
2138	b0d20d28	AGV02	go_to	2	queued	2026-06-06 15:15:26.78987+07	\N	\N	\N	mq22v05tjey4g7sdvk	A06
2139	92e07eac	AGV02	go_to	1	queued	2026-06-06 15:15:32.90087+07	\N	\N	\N	mq22v05tjey4g7sdvk	A06
2137	ddc79e1e	AGV02	go_to	2	completed	2026-06-06 15:15:26.650824+07	2026-06-06 15:15:26.686796+07	2026-06-06 15:15:32.901871+07	off_route	mq22v05tjey4g7sdvk	A06
2140	e6ff0f75	AGV02	go_to	1	queued	2026-06-06 15:15:33.080099+07	\N	\N	\N	mq22v05tjey4g7sdvk	A06
2153	171aea68	AGV02	go_to	19	completed	2026-06-08 09:39:14.189081+07	2026-06-08 09:39:40.245822+07	2026-06-08 09:40:16.817319+07	lifecycle:picking:confirmed	mq4lr4lbl3a96pfed	A06
2131	9fb5f073	AGV01	go_to	17	completed	2026-06-06 15:14:33.632894+07	2026-06-06 15:15:07.584157+07	2026-06-06 15:15:41.467566+07	lifecycle:picking:confirmed	mq22unfg1pp32z2m33o	A06
2142	3aa2d752	AGV02	go_to	96	queued	2026-06-06 15:15:44.202932+07	\N	\N	\N	mq22v05tjey4g7sdvk	A06
2130	b1c92c8b	AGV01	go_charge	\N	completed	2026-06-06 15:14:33.633898+07	2026-06-06 15:15:41.467566+07	2026-06-06 15:15:57.447157+07		mq22unfg1pp32z2m33o	A06
2163	87b75a49	AGV01	go_charge	\N	completed	2026-06-08 10:57:19.147721+07	2026-06-08 10:58:23.9622+07	2026-06-08 10:58:39.728337+07		mq4ojjd8emd53ucdkvq	A06
2141	282fce38	AGV01	go_charge	\N	completed	2026-06-06 15:15:41.491564+07	2026-06-06 15:15:57.448674+07	2026-06-06 15:16:49.148451+07	charge_arrived	mq22unfg1pp32z2m33o	A06
2143	a6977f73	AGV01	go_to	96	running	2026-06-08 08:28:00.222651+07	\N	\N	\N	4ad32cd9	Lấy hàng
2144	92d22b40	AGV01	go_charge	\N	queued	2026-06-08 08:28:00.377272+07	\N	\N	\N	4ad32cd9	Lấy hàng
2145	11c98718	AGV01	go_to	96	queued	2026-06-08 08:28:00.37526+07	\N	\N	\N	4ad32cd9	Lấy hàng
2146	bd4ac20b	AGV02	go_to	69	running	2026-06-08 08:28:00.522681+07	\N	\N	\N	ff7653d4	Lịch 140c10
2147	c2950e1a	AGV02	go_to	69	queued	2026-06-08 08:28:00.533298+07	\N	\N	\N	ff7653d4	Lịch 140c10
2148	d0abb333	AGV02	go_charge	\N	queued	2026-06-08 08:28:00.534319+07	\N	\N	\N	ff7653d4	Lịch 140c10
2149	55451e75	AGV01	go_to	19	completed	2026-06-08 09:38:55.044505+07	2026-06-08 09:38:55.044505+07	2026-06-08 09:39:30.029054+07	lifecycle:picking:confirmed	mq4lqpsrtxq6iulozub	A06
2151	fa75403e	AGV01	go_charge	\N	completed	2026-06-08 09:38:55.087556+07	2026-06-08 09:40:08.691037+07	2026-06-08 09:40:25.766551+07	off_route	mq4lqpsrtxq6iulozub	A06
2154	84a75d38	AGV02	go_to	17	completed	2026-06-08 09:39:14.211603+07	2026-06-08 09:40:16.866332+07	2026-06-08 09:41:13.1784+07	off_route	mq4lr4lbl3a96pfed	A06
2159	82763bc8	AGV02	go_to	9	completed	2026-06-08 09:41:13.177401+07	2026-06-08 09:41:13.1794+07	2026-06-08 09:41:30.000348+07		mq4lr4lbl3a96pfed	A06
2161	4a98f4a4	AGV02	go_charge	\N	completed	2026-06-08 09:44:33.801916+07	2026-06-08 09:44:48.973339+07	2026-06-08 09:45:37.890958+07	charge_arrived	mq4lr4lbl3a96pfed	A06
2160	e4446246	AGV02	go_to	9	completed	2026-06-08 09:41:13.194958+07	2026-06-08 09:41:30.006382+07	2026-06-08 09:43:26.138506+07	lifecycle:picking:confirmed	mq4lr4lbl3a96pfed	A06
2156	66005f6d	AGV01	go_charge	\N	completed	2026-06-08 09:40:08.875546+07	2026-06-08 09:45:22.114879+07	2026-06-08 09:46:18.891223+07	charge_arrived	mq4lqpsrtxq6iulozub	A06
2166	5e9d1b38	AGV02	go_to	19	completed	2026-06-08 10:57:34.248992+07	2026-06-08 10:57:53.92006+07	2026-06-08 10:57:54.028294+07	dest_wait	mq4ojv46ifejuq6wmi	A06
2158	ef15cd30	AGV02	go_to	17	completed	2026-06-08 09:40:36.424416+07	2026-06-08 09:43:26.138506+07	2026-06-08 09:44:33.6508+07	lifecycle:picking:confirmed	mq4lr4lbl3a96pfed	A06
2167	2bf37cfd	AGV02	go_to	17	completed	2026-06-08 10:57:34.517671+07	2026-06-08 10:57:54.029296+07	2026-06-08 10:58:17.898172+07	lifecycle:picking:confirmed	mq4ojv46ifejuq6wmi	A06
2162	9a11805f	AGV01	go_to	19	completed	2026-06-08 10:57:18.977665+07	2026-06-08 10:57:18.977665+07	2026-06-08 10:58:01.275821+07	lifecycle:picking:confirmed	mq4ojjd8emd53ucdkvq	A06
2172	dc438123	AGV01	go_charge	\N	cancelled	2026-06-08 11:01:56.384517+07	2026-06-08 11:01:56.384517+07	2026-06-08 11:03:40.759293+07	force-cancelled by user	mq4ophgyc56dz9lmnic	Sạc Pin
2168	293d207a	AGV02	go_charge	\N	cancelled	2026-06-08 10:57:34.531667+07	\N	2026-06-08 11:01:02.400199+07	cancelled by user	mq4ojv46ifejuq6wmi	A06
2164	b1381503	AGV01	go_to	17	completed	2026-06-08 10:57:19.146724+07	2026-06-08 10:58:01.275821+07	2026-06-08 10:58:23.9622+07	lifecycle:picking:confirmed	mq4ojjd8emd53ucdkvq	A06
2169	92490bec	AGV02	go_to	17	cancelled	2026-06-08 10:57:54.039307+07	2026-06-08 10:58:17.898172+07	2026-06-08 11:01:02.399199+07	force-cancelled by user	mq4ojv46ifejuq6wmi	A06
2170	bbcbcf19	AGV02	go_to	17	cancelled	2026-06-08 10:58:17.919401+07	\N	2026-06-08 11:01:02.400199+07	cancelled by user	mq4ojv46ifejuq6wmi	A06
2171	4557e3c5	AGV01	go_charge	\N	cancelled	2026-06-08 10:58:23.979721+07	2026-06-08 10:58:39.72932+07	2026-06-08 11:01:10.459702+07	force-cancelled by user	mq4ojjd8emd53ucdkvq	A06
2173	44d9f3c7	AGV01	go_charge	\N	completed	2026-06-08 11:03:49.447424+07	2026-06-08 11:03:49.447424+07	2026-06-08 11:04:04.279166+07		mq4orwpjti0bloc5x0r	Sạc Pin
2175	c6f350ad	AGV02	go_charge	\N	cancelled	2026-06-08 11:04:01.291128+07	2026-06-08 11:04:01.291128+07	2026-06-08 11:05:46.134413+07	force-cancelled by user	mq4os5ub6nu4xh3tnsn	Sạc Pin
2174	9ca88cca	AGV01	go_charge	\N	completed	2026-06-08 11:03:49.469425+07	2026-06-08 11:04:04.283184+07	2026-06-08 11:04:52.483146+07	charge_arrived	mq4orwpjti0bloc5x0r	Sạc Pin
2176	68230bfe	AGV02	go_charge	\N	cancelled	2026-06-08 11:05:55.562972+07	2026-06-08 11:05:55.562972+07	2026-06-08 11:06:05.784531+07	force-cancelled by user	mq4oum09g03catw7lc6	Sạc Pin
2177	ab449ccd	AGV02	go_charge	\N	cancelled	2026-06-08 11:05:55.577802+07	\N	2026-06-08 11:06:05.792527+07	cancelled by user	mq4oum09g03catw7lc6	Sạc Pin
2181	df6345bb	AGV01	go_to	19	completed	2026-06-08 11:08:06.615447+07	2026-06-08 11:08:06.615447+07	2026-06-08 11:08:19.844829+07		mq4oxf4uua8dtmag4t	A06
2198	778c8cc7	AGV01	go_to	19	completed	2026-06-08 14:08:10.89393+07	2026-06-08 14:08:10.89393+07	2026-06-08 14:08:48.956215+07	lifecycle:picking:confirmed	mq4vczqop71sj816aah	A06
2178	2f2c96e2	AGV02	go_to	19	completed	2026-06-08 11:07:53.45293+07	2026-06-08 11:07:53.451926+07	2026-06-08 11:08:29.24724+07	lifecycle:picking:confirmed	mq4ox4xv451clps5key	A06
2219	0168eaaf	AGV02	go_charge	\N	cancelled	2026-06-08 14:54:38.541956+07	\N	2026-06-08 14:54:49.589521+07	cancelled by user	mq4x0qpk6xm4u42pda	Sạc Pin
2182	c4d7cdd3	AGV01	go_to	19	completed	2026-06-08 11:08:06.619452+07	2026-06-08 11:08:19.845825+07	2026-06-08 11:08:41.217959+07		mq4oxf4uua8dtmag4t	A06
2180	87211fed	AGV02	go_to	17	completed	2026-06-08 11:07:53.502444+07	2026-06-08 11:08:29.24824+07	2026-06-08 11:09:02.760903+07	lifecycle:picking:confirmed	mq4ox4xv451clps5key	A06
2201	f171b02b	AGV02	go_to	19	completed	2026-06-08 14:08:28.731721+07	2026-06-08 14:08:28.731721+07	2026-06-08 14:08:55.39608+07		mq4vddj2s2mpxfe0ktf	A06
2185	24f7bed8	AGV01	go_to	19	completed	2026-06-08 11:08:19.999391+07	2026-06-08 11:08:41.218974+07	2026-06-08 11:09:08.821266+07	lifecycle:picking:confirmed	mq4oxf4uua8dtmag4t	A06
2200	95fbcff4	AGV01	go_to	17	completed	2026-06-08 14:08:11.059573+07	2026-06-08 14:08:48.959231+07	2026-06-08 14:10:20.096698+07	lifecycle:picking:confirmed	mq4vczqop71sj816aah	A06
2179	859e546d	AGV02	go_charge	\N	completed	2026-06-08 11:07:53.504461+07	2026-06-08 11:09:02.761887+07	2026-06-08 11:09:17.859936+07		mq4ox4xv451clps5key	A06
2186	8e46ac39	AGV02	go_charge	\N	cancelled	2026-06-08 11:09:02.905406+07	2026-06-08 11:09:17.860936+07	2026-06-08 11:46:48.800296+07	force-cancelled by user	mq4ox4xv451clps5key	A06
2183	e7630990	AGV01	go_to	17	cancelled	2026-06-08 11:08:06.62949+07	2026-06-08 11:09:08.821266+07	2026-06-08 11:46:52.846055+07	force-cancelled by user	mq4oxf4uua8dtmag4t	A06
2184	fd24645d	AGV01	go_charge	\N	cancelled	2026-06-08 11:08:06.630447+07	\N	2026-06-08 11:46:52.846562+07	cancelled by user	mq4oxf4uua8dtmag4t	A06
2190	7870c937	AGV02	go_to	19	completed	2026-06-08 13:33:20.468854+07	2026-06-08 13:33:20.468854+07	2026-06-08 13:33:34.409164+07		mq4u46r15lnf2pmptgd	A06
2202	a6eda1a0	AGV02	go_to	19	completed	2026-06-08 14:08:28.740904+07	2026-06-08 14:08:55.39708+07	2026-06-08 14:10:22.488067+07	lifecycle:picking:confirmed	mq4vddj2s2mpxfe0ktf	A06
2187	1c719c4a	AGV01	go_to	19	completed	2026-06-08 13:33:08.55013+07	2026-06-08 13:33:08.55013+07	2026-06-08 13:33:43.789082+07	lifecycle:picking:confirmed	mq4u3xk5m1zslvzba5a	A06
2191	0047cf5a	AGV02	go_to	19	completed	2026-06-08 13:33:20.495468+07	2026-06-08 13:33:34.410396+07	2026-06-08 13:33:54.937987+07		mq4u46r15lnf2pmptgd	A06
2213	5f016507	AGV02	go_to	17	completed	2026-06-08 14:42:38.836887+07	2026-06-08 14:50:44.254378+07	2026-06-08 14:50:59.309039+07		mq4wk6v3bvukoc1i1dp	A06
2188	20d68c86	AGV01	go_to	17	completed	2026-06-08 13:33:08.739782+07	2026-06-08 13:33:43.789082+07	2026-06-08 13:34:06.814514+07	lifecycle:picking:confirmed	mq4u3xk5m1zslvzba5a	A06
2203	3c31cf2d	AGV02	go_to	17	cancelled	2026-06-08 14:08:28.766436+07	2026-06-08 14:10:22.488067+07	2026-06-08 14:28:12.67462+07	force-cancelled by user	mq4vddj2s2mpxfe0ktf	A06
2194	42c562ac	AGV02	go_to	19	completed	2026-06-08 13:33:34.632403+07	2026-06-08 13:33:54.943965+07	2026-06-08 13:34:11.851155+07	lifecycle:picking:confirmed	mq4u46r15lnf2pmptgd	A06
2204	2c0fd5f9	AGV02	go_charge	\N	cancelled	2026-06-08 14:08:28.769455+07	\N	2026-06-08 14:28:12.690627+07	cancelled by user	mq4vddj2s2mpxfe0ktf	A06
2189	55121207	AGV01	go_charge	\N	completed	2026-06-08 13:33:08.741767+07	2026-06-08 13:34:06.81551+07	2026-06-08 13:34:22.545263+07		mq4u3xk5m1zslvzba5a	A06
2199	ce605b31	AGV01	go_charge	\N	completed	2026-06-08 14:08:11.060583+07	2026-06-08 14:10:20.097696+07	2026-06-08 14:28:28.989068+07		mq4vczqop71sj816aah	A06
2192	455e8657	AGV02	go_to	17	cancelled	2026-06-08 13:33:20.533458+07	2026-06-08 13:34:11.852168+07	2026-06-08 14:00:59.483412+07	force-cancelled by user	mq4u46r15lnf2pmptgd	A06
2193	2fa37d24	AGV02	go_charge	\N	cancelled	2026-06-08 13:33:20.535986+07	\N	2026-06-08 14:00:59.484415+07	cancelled by user	mq4u46r15lnf2pmptgd	A06
2196	e455cf3d	AGV02	go_charge	\N	cancelled	2026-06-08 14:01:10.189452+07	2026-06-08 14:01:10.189452+07	2026-06-08 14:01:19.938051+07	force-cancelled by user	mq4v3z5i9dnpcx38uhh	Sạc Pin
2197	539fb678	AGV02	go_charge	\N	cancelled	2026-06-08 14:01:10.21345+07	\N	2026-06-08 14:01:19.944056+07	cancelled by user	mq4v3z5i9dnpcx38uhh	Sạc Pin
2195	f38c1ba3	AGV01	go_charge	\N	cancelled	2026-06-08 13:34:06.830524+07	2026-06-08 13:34:22.545263+07	2026-06-08 14:01:29.612409+07	force-cancelled by user	mq4u3xk5m1zslvzba5a	A06
2205	6fec540a	AGV01	go_charge	\N	completed	2026-06-08 14:10:20.119701+07	2026-06-08 14:28:28.990176+07	2026-06-08 14:29:24.502012+07	charge_arrived	mq4vczqop71sj816aah	A06
2206	c9988101	AGV01	go_to	19	completed	2026-06-08 14:41:31.701036+07	2026-06-08 14:41:31.701036+07	2026-06-08 14:42:06.325073+07	lifecycle:picking:confirmed	mq4wjvl6my2rrl7spwn	A06
2208	2b5ce4cd	AGV01	go_to	17	cancelled	2026-06-08 14:41:31.745767+07	2026-06-08 14:42:06.325073+07	2026-06-08 14:51:20.617283+07	force-cancelled by user	mq4wjvl6my2rrl7spwn	A06
2209	f173acb8	AGV02	go_to	19	completed	2026-06-08 14:41:46.343178+07	2026-06-08 14:41:46.343178+07	2026-06-08 14:42:15.655202+07		mq4wk6v3bvukoc1i1dp	A06
2210	4e68b123	AGV02	go_to	19	completed	2026-06-08 14:41:46.374176+07	2026-06-08 14:42:15.66182+07	2026-06-08 14:42:38.826325+07	lifecycle:picking:confirmed	mq4wk6v3bvukoc1i1dp	A06
2207	f6e893cf	AGV01	go_charge	\N	cancelled	2026-06-08 14:41:31.747765+07	\N	2026-06-08 14:51:20.617283+07	cancelled by user	mq4wjvl6my2rrl7spwn	A06
2211	6652db52	AGV02	go_to	17	completed	2026-06-08 14:41:46.402175+07	2026-06-08 14:42:38.826325+07	2026-06-08 14:50:44.253332+07		mq4wk6v3bvukoc1i1dp	A06
2214	a29e1214	AGV02	go_to	17	cancelled	2026-06-08 14:50:44.573347+07	2026-06-08 14:50:59.309039+07	2026-06-08 14:53:01.930516+07	force-cancelled by user	mq4wk6v3bvukoc1i1dp	A06
2215	44aa7a48	AGV02	go_to	17	cancelled	2026-06-08 14:50:59.322039+07	\N	2026-06-08 14:53:01.931517+07	cancelled by user	mq4wk6v3bvukoc1i1dp	A06
2212	579ab54b	AGV02	go_charge	\N	cancelled	2026-06-08 14:41:46.403175+07	\N	2026-06-08 14:53:01.931517+07	cancelled by user	mq4wk6v3bvukoc1i1dp	A06
2216	1510e797	AGV02	go_charge	\N	completed	2026-06-08 14:53:11.370181+07	2026-06-08 14:53:11.370181+07	2026-06-08 14:53:25.906629+07		mq4wyvgr6rpoc316uxn	Sạc Pin
2217	425ea0eb	AGV02	go_charge	\N	cancelled	2026-06-08 14:53:11.393547+07	2026-06-08 14:53:25.907622+07	2026-06-08 14:54:25.689462+07	force-cancelled by user	mq4wyvgr6rpoc316uxn	Sạc Pin
2218	0455e9e2	AGV02	go_charge	\N	cancelled	2026-06-08 14:54:38.520562+07	2026-06-08 14:54:38.520562+07	2026-06-08 14:54:49.589521+07	force-cancelled by user	mq4x0qpk6xm4u42pda	Sạc Pin
2223	1900b0e8	AGV02	go_to	19	completed	2026-06-08 14:59:52.837074+07	2026-06-08 14:59:52.837074+07	2026-06-08 15:00:06.393423+07		mq4x7h7uslkf06bs6r	A06
2226	83f3f251	AGV02	go_charge	\N	cancelled	2026-06-08 14:59:52.859603+07	\N	2026-06-08 15:04:02.942955+07	cancelled by user	mq4x7h7uslkf06bs6r	A06
2220	4a781652	AGV01	go_to	19	completed	2026-06-08 14:59:39.055678+07	2026-06-08 14:59:39.055678+07	2026-06-08 15:00:13.307564+07	lifecycle:picking:confirmed	mq4x76ljsozgsynn6p	A06
2225	1afe7dde	AGV02	go_to	17	completed	2026-06-08 14:59:52.858605+07	2026-06-08 15:00:45.435487+07	2026-06-08 15:01:02.342039+07		mq4x7h7uslkf06bs6r	A06
2224	1d577516	AGV02	go_to	19	completed	2026-06-08 14:59:52.842605+07	2026-06-08 15:00:06.394427+07	2026-06-08 15:00:26.519139+07		mq4x7h7uslkf06bs6r	A06
2221	cb0a6c66	AGV01	go_to	17	completed	2026-06-08 14:59:39.111803+07	2026-06-08 15:00:13.307564+07	2026-06-08 15:00:53.387364+07	lifecycle:picking:confirmed	mq4x76ljsozgsynn6p	A06
2227	64394fe8	AGV02	go_to	19	completed	2026-06-08 15:00:06.523291+07	2026-06-08 15:00:26.519139+07	2026-06-08 15:00:45.435487+07	lifecycle:picking:confirmed	mq4x7h7uslkf06bs6r	A06
2228	5bbf602b	AGV02	go_to	17	cancelled	2026-06-08 15:00:45.447485+07	2026-06-08 15:01:02.343028+07	2026-06-08 15:04:02.939955+07	force-cancelled by user	mq4x7h7uslkf06bs6r	A06
2222	8fe0100b	AGV01	go_charge	\N	completed	2026-06-08 14:59:39.115707+07	2026-06-08 15:00:53.387364+07	2026-06-08 15:01:09.338319+07		mq4x76ljsozgsynn6p	A06
2232	ded569b5	AGV01	go_to	19	completed	2026-06-08 15:12:22.482075+07	2026-06-08 15:12:22.482075+07	2026-06-08 15:12:58.535237+07	lifecycle:picking:confirmed	mq4xnjnkq1klpcf74s	A06
2230	4e2a7865	AGV02	go_charge	\N	cancelled	2026-06-08 15:04:08.243473+07	2026-06-08 15:04:08.243473+07	2026-06-08 15:04:43.893008+07	force-cancelled by user	mq4xcybj0ik8c2zqzo7o	Sạc Pin
2231	e5e7c282	AGV02	go_charge	\N	cancelled	2026-06-08 15:04:08.283029+07	\N	2026-06-08 15:04:43.893008+07	cancelled by user	mq4xcybj0ik8c2zqzo7o	Sạc Pin
2229	a2caab04	AGV01	go_charge	\N	completed	2026-06-08 15:00:53.403406+07	2026-06-08 15:01:09.339313+07	2026-06-08 15:06:20.96884+07	charge_arrived	mq4x76ljsozgsynn6p	A06
2235	01b0d092	AGV02	go_to	19	completed	2026-06-08 15:12:39.692849+07	2026-06-08 15:12:39.692849+07	2026-06-08 15:13:06.349184+07		mq4xnwxvwqy5a6urhe	A06
2798	2cff3d22	AGV01	go_charge	\N	cancelled	2026-06-15 10:59:36.151879+07	2026-06-15 10:59:36.151862+07	2026-06-15 11:01:41.054679+07	force-cancelled by user	mqeopfx5b3wss8vf0x9	Sạc Pin
2234	5b0a64c4	AGV01	go_charge	\N	completed	2026-06-08 15:12:22.515972+07	2026-06-08 15:13:22.892997+07	2026-06-08 15:13:38.679257+07		mq4xnjnkq1klpcf74s	A06
2238	44d3a46f	AGV02	go_charge	\N	completed	2026-06-08 15:12:39.807999+07	2026-06-08 15:14:47.235983+07	2026-06-08 15:15:32.458146+07	charge_arrived	mq4xnwxvwqy5a6urhe	A06
2243	37d65c49	AGV01	go_to	19	completed	2026-06-08 15:15:56.26422+07	2026-06-08 15:15:56.26422+07	2026-06-08 15:16:09.611902+07		mq4xs4n3dp5uqazu50d	A06
2801	b0ad216d	AGV01	go_charge	\N	completed	2026-06-15 11:02:37.014847+07	2026-06-15 11:02:37.014842+07	2026-06-15 11:02:53.26058+07		mqeotbh79fgg9bybq6	Sạc Pin
2240	07d2958c	AGV02	go_to	19	completed	2026-06-08 15:15:43.575029+07	2026-06-08 15:15:43.575029+07	2026-06-08 15:16:14.949748+07	lifecycle:picking:confirmed	mq4xrutzgwyd6l6mmze	A06
2861	2d4733f4	AGV01	go_to	19	completed	2026-06-15 13:30:12.390214+07	2026-06-15 13:30:12.390204+07	2026-06-15 13:30:45.261536+07	lifecycle:picking:confirmed	mqeu34ayd34lw23ffis	A06
2242	f4803897	AGV02	go_charge	\N	completed	2026-06-08 15:15:43.628029+07	2026-06-08 15:16:42.382848+07	2026-06-08 15:16:57.492389+07		mq4xrutzgwyd6l6mmze	A06
2248	143d1a9a	AGV02	go_charge	\N	completed	2026-06-08 15:16:42.399849+07	2026-06-08 15:16:57.49478+07	2026-06-08 15:18:51.672287+07	charge_arrived	mq4xrutzgwyd6l6mmze	A06
2244	1fbc8d0c	AGV01	go_to	19	cancelled	2026-06-08 15:15:56.271222+07	2026-06-08 15:16:09.613005+07	2026-06-08 15:19:09.796871+07	force-cancelled by user	mq4xs4n3dp5uqazu50d	A06
2246	50524272	AGV01	go_charge	\N	cancelled	2026-06-08 15:15:56.291738+07	\N	2026-06-08 15:19:09.796871+07	cancelled by user	mq4xs4n3dp5uqazu50d	A06
2868	e6309167	AGV02	go_to	19	completed	2026-06-15 13:30:32.338854+07	2026-06-15 13:30:54.333342+07	2026-06-15 13:31:35.891666+07	lifecycle:picking:confirmed	mqeu3a834kzk9u5zgw8	A06
2950	98e033fe	AGV02	go_to	18	cancelled	2026-06-16 09:30:47.496323+07	2026-06-16 09:31:01.135135+07	2026-06-16 09:33:01.14067+07	force-cancelled by user	mqg0x7b92ot2vi46f33	A02
3357	051bd250	AGV01	go_to	19	completed	2026-06-17 16:05:02.829425+07	2026-06-17 16:05:02.829425+07	2026-06-17 16:05:39.585972+07	lifecycle:picking:confirmed	mqhuhy6aq5oqwhj80ab	A05
3005	ede0415e	AGV01	go_to	19	completed	2026-06-16 10:41:45.546402+07	2026-06-16 10:41:45.546391+07	2026-06-16 10:42:17.263693+07	lifecycle:picking:confirmed	mqg3ichgv8wg7olmg0n	A06
3009	5a77061f	AGV02	go_to	19	completed	2026-06-16 10:41:53.900673+07	2026-06-16 10:42:06.047159+07	2026-06-16 10:42:27.15897+07		mqg3iixvmxwiizjkz9	A06
3132	7a9ee137	AGV01	go_charge	14	completed	2026-06-16 14:10:11.79892+07	2026-06-16 14:10:11.800861+07	2026-06-16 14:10:26.826968+07		mqgaxmv7tvrdzj73j8j	Sạc Pin
3007	961bbe45	AGV01	go_charge	\N	completed	2026-06-16 10:41:45.707074+07	2026-06-16 10:43:20.828187+07	2026-06-16 10:43:35.747642+07		mqg3ichgv8wg7olmg0n	A06
3133	cfb58622	AGV01	go_charge	\N	completed	2026-06-16 14:10:11.82369+07	2026-06-16 14:10:26.828286+07	2026-06-16 14:11:17.885458+07	charge_arrived	mqgaxmv7tvrdzj73j8j	Sạc Pin
3011	418e8198	AGV02	go_charge	\N	completed	2026-06-16 10:41:53.915736+07	2026-06-16 10:44:45.286806+07	2026-06-16 10:44:59.450449+07		mqg3iixvmxwiizjkz9	A06
3016	1413d3d2	AGV02	go_charge	\N	completed	2026-06-16 10:44:45.298723+07	2026-06-16 10:44:59.450993+07	2026-06-16 10:46:12.01994+07	charge_arrived	mqg3iixvmxwiizjkz9	A06
3021	af57e2cc	AGV02	go_to	19	completed	2026-06-16 10:48:25.913677+07	2026-06-16 10:48:25.91366+07	2026-06-16 10:48:25.925891+07	dest_wait	mqg3qxf0a9s02v2wlwc	A02
3022	8b2d3d75	AGV02	go_to	16	completed	2026-06-16 10:48:25.927046+07	2026-06-16 10:48:25.927039+07	2026-06-16 10:49:11.413365+07	lifecycle:picking:confirmed	mqg3qxf0a9s02v2wlwc	A02
3020	80065156	AGV01	go_charge	\N	completed	2026-06-16 10:48:07.540312+07	2026-06-16 10:50:03.014462+07	2026-06-16 10:51:28.154608+07	charge_arrived	mqg3qj4r96h1k4wlry	A02
3068	f8e1035b	AGV01	go_to	19	completed	2026-06-16 11:54:39.360809+07	2026-06-16 11:55:24.555588+07	2026-06-16 11:55:24.566305+07	dest_wait	mqg643a9yx8rzeckwg7	A05
3089	8deeb677	AGV01	go_to	15	cancelled	2026-06-16 11:59:33.661073+07	\N	2026-06-16 13:11:26.29116+07	cancelled by user	mqg643a9yx8rzeckwg7	A05
3070	556543ab	AGV01	go_to	18	cancelled	2026-06-16 11:54:39.374186+07	\N	2026-06-16 13:11:26.29116+07	cancelled by user	mqg643a9yx8rzeckwg7	A05
3135	7754500a	AGV01	go_to	19	completed	2026-06-16 14:15:24.661144+07	2026-06-16 14:16:04.922159+07	2026-06-16 14:16:19.884471+07	lifecycle:picking:confirmed	mqgb53r3i1fjyn17vf	A05
3120	cd586e81	AGV02	go_to	19	completed	2026-06-16 14:04:58.097276+07	2026-06-16 14:04:58.097266+07	2026-06-16 14:06:10.802154+07	lifecycle:picking:confirmed	mqgarobeo6pxyf1spq	A02
3124	77363b1b	AGV01	go_to	96	completed	2026-06-16 14:05:36.688727+07	2026-06-16 14:05:53.917678+07	2026-06-16 14:06:11.894629+07	off_route	mqgareo2r995j36a5q	A05
3126	5bde0c11	AGV01	go_to	9	completed	2026-06-16 14:06:11.893906+07	2026-06-16 14:06:11.895032+07	2026-06-16 14:06:26.577974+07		mqgareo2r995j36a5q	A05
3122	e424f8e5	AGV02	go_to	18	completed	2026-06-16 14:04:58.121421+07	2026-06-16 14:07:24.942792+07	2026-06-16 14:07:42.85897+07		mqgarobeo6pxyf1spq	A02
3119	58272276	AGV01	go_to	69	cancelled	2026-06-16 14:04:45.949964+07	\N	2026-06-16 14:09:29.433686+07	cancelled by user	mqgareo2r995j36a5q	A05
3182	b47ab1cb	AGV01	go_charge	\N	completed	2026-06-16 16:04:15.484521+07	2026-06-16 16:05:43.85569+07	2026-06-16 16:05:58.782466+07		mqgf12s0v316bse7prh	A02
3148	e9007adb	AGV01	go_to	9	completed	2026-06-16 14:16:55.315152+07	2026-06-16 14:17:08.376665+07	2026-06-16 14:17:32.572792+07	lifecycle:picking:confirmed	mqgb53r3i1fjyn17vf	A05
3155	f645ba8d	AGV02	go_to	18	completed	2026-06-16 14:20:53.364884+07	2026-06-16 14:21:07.320538+07	2026-06-16 14:21:45.130492+07	event:continue	mqgb5deppduqstpidij	A02
3259	14fc4af2	AGV02	go_to	18	completed	2026-06-17 14:26:19.335261+07	2026-06-17 14:28:49.25422+07	2026-06-17 14:29:03.906482+07		mqhqyzkaa3unckw0oin	A05
3137	1b03f4cb	AGV01	go_to	17	completed	2026-06-16 14:15:24.67048+07	2026-06-16 14:23:36.69547+07	2026-06-16 14:24:44.7936+07	lifecycle:picking:confirmed	mqgb53r3i1fjyn17vf	A05
3188	768b55bf	AGV01	go_charge	\N	completed	2026-06-16 16:05:43.878654+07	2026-06-16 16:05:58.782466+07	2026-06-16 16:07:10.291809+07	charge_arrived	mqgf12s0v316bse7prh	A02
3158	717885ab	AGV01	go_charge	\N	cancelled	2026-06-16 14:26:42.148615+07	\N	2026-06-16 14:26:57.845198+07	cancelled by user	mqgbjmj463wg5wo411v	Sạc Pin
3159	69a57256	AGV01	go_to	2	cancelled	2026-06-16 14:26:57.059367+07	2026-06-16 14:26:57.060374+07	2026-06-16 14:26:57.844932+07	force-cancelled by user	mqgbjmj463wg5wo411v	Sạc Pin
3183	aed70f63	AGV02	go_to	19	completed	2026-06-16 16:04:29.213734+07	2026-06-16 16:04:29.213734+07	2026-06-16 16:04:57.804573+07		mqgf1dkeaiwatba55uo	A02
3187	1ae7ec14	AGV02	go_charge	\N	completed	2026-06-16 16:04:29.252742+07	2026-06-16 16:06:54.856847+07	2026-06-16 16:08:11.622684+07	off_route	mqgf1dkeaiwatba55uo	A02
3252	e707773b	AGV01	go_to	16	completed	2026-06-17 14:25:57.190086+07	2026-06-17 14:26:58.073706+07	2026-06-17 14:27:42.243888+07	event:continue	mqhqyibpsjmtqtixyk	A05
3257	9b2f2d2c	AGV02	go_to	19	completed	2026-06-17 14:26:19.298492+07	2026-06-17 14:26:21.588147+07	2026-06-17 14:26:45.2521+07		mqhqyzkaa3unckw0oin	A05
3264	6ca6bcb0	AGV02	go_to	16	completed	2026-06-17 14:27:18.245648+07	2026-06-17 14:27:34.96234+07	2026-06-17 14:27:51.607239+07		mqhqyzkaa3unckw0oin	A05
3321	86350642	AGV01	go_to	15	completed	2026-06-17 15:25:30.291237+07	2026-06-17 15:25:52.71354+07	2026-06-17 15:26:16.282408+07		mqht10otruzwoswgsvq	A05
3266	cdecadcc	AGV01	go_to	15	completed	2026-06-17 14:27:42.260307+07	2026-06-17 14:28:01.491324+07	2026-06-17 14:28:15.427613+07	event:continue	mqhqyibpsjmtqtixyk	A05
3254	7a700734	AGV01	go_charge	\N	cancelled	2026-06-17 14:25:57.203114+07	2026-06-17 14:29:14.387366+07	2026-06-17 14:37:48.193213+07	force-cancelled by user	mqhqyibpsjmtqtixyk	A05
3261	7adf3e5e	AGV02	go_to	15	cancelled	2026-06-17 14:26:19.344114+07	\N	2026-06-17 14:37:55.150819+07	cancelled by user	mqhqyzkaa3unckw0oin	A05
3326	683251a4	AGV02	go_to	18	completed	2026-06-17 15:29:31.362671+07	2026-06-17 15:29:31.362671+07	2026-06-17 15:30:08.420337+07	lifecycle:picking:confirmed	mqht1i431tvwdr671ixh	yield_resume
3375	57592e4e	AGV02	go_to	18	completed	2026-06-17 16:09:14.104768+07	2026-06-17 16:09:14.104768+07	2026-06-17 16:09:28.43856+07	off_route	mqhuifm91ep4iqf2s27	yield_resume
3370	74cc2c54	AGV02	go_to	19	completed	2026-06-17 16:05:27.73403+07	2026-06-17 16:05:49.398516+07	2026-06-17 16:07:28.812632+07	lifecycle:picking:confirmed	mqhuifm91ep4iqf2s27	A05
3358	b8b706ae	AGV01	go_to	15	completed	2026-06-17 16:05:02.862037+07	2026-06-17 16:06:14.325126+07	2026-06-17 16:06:31.954242+07		mqhuhy6aq5oqwhj80ab	A05
3360	61cdf835	AGV01	go_to	16	completed	2026-06-17 16:05:02.870037+07	2026-06-17 16:08:17.58331+07	2026-06-17 16:09:24.930409+07	event:continue	mqhuhy6aq5oqwhj80ab	A05
3367	7e4d3dd0	AGV02	go_to	17	completed	2026-06-17 16:05:25.47674+07	2026-06-17 16:11:27.396018+07	2026-06-17 16:11:42.262327+07		mqhuifm91ep4iqf2s27	A05
2233	9aa0db21	AGV01	go_to	17	completed	2026-06-08 15:12:22.514972+07	2026-06-08 15:12:58.535237+07	2026-06-08 15:13:22.892997+07	lifecycle:picking:confirmed	mq4xnjnkq1klpcf74s	A06
2236	7559487b	AGV02	go_to	19	completed	2026-06-08 15:12:39.770426+07	2026-06-08 15:13:06.350182+07	2026-06-08 15:13:35.586351+07	lifecycle:picking:confirmed	mq4xnwxvwqy5a6urhe	A06
2239	d92bf9b0	AGV01	go_charge	\N	completed	2026-06-08 15:13:22.908+07	2026-06-08 15:13:38.679257+07	2026-06-08 15:14:45.575639+07	charge_arrived	mq4xnjnkq1klpcf74s	A06
2237	bbad8217	AGV02	go_to	17	completed	2026-06-08 15:12:39.805995+07	2026-06-08 15:13:35.586351+07	2026-06-08 15:14:47.235983+07	lifecycle:picking:confirmed	mq4xnwxvwqy5a6urhe	A06
2803	b4884fcd	AGV01	go_to	19	completed	2026-06-15 11:13:03.276262+07	2026-06-15 11:13:03.276216+07	2026-06-15 11:13:34.847039+07	lifecycle:picking:confirmed	mqep6qo99u0kysy66rp	A06
2241	fe25c617	AGV02	go_to	17	completed	2026-06-08 15:15:43.62603+07	2026-06-08 15:16:14.952804+07	2026-06-08 15:16:42.382848+07	lifecycle:picking:confirmed	mq4xrutzgwyd6l6mmze	A06
2245	cc2fb92b	AGV01	go_to	17	cancelled	2026-06-08 15:15:56.29074+07	\N	2026-06-08 15:19:09.796871+07	cancelled by user	mq4xs4n3dp5uqazu50d	A06
2807	a6e49c51	AGV02	go_to	19	completed	2026-06-15 11:13:15.388985+07	2026-06-15 11:13:46.168061+07	2026-06-15 11:14:17.567216+07	lifecycle:picking:confirmed	mqep701fccyw9me06sw	A06
2804	ea5a93d7	AGV01	go_charge	\N	completed	2026-06-15 11:13:03.93795+07	2026-06-15 11:14:09.165418+07	2026-06-15 11:14:24.229264+07		mqep6qo99u0kysy66rp	A06
2809	6050b4fb	AGV02	go_charge	\N	completed	2026-06-15 11:13:15.407242+07	2026-06-15 11:19:15.990697+07	2026-06-15 11:19:30.470225+07		mqep701fccyw9me06sw	A06
2871	1f1cf08d	AGV01	go_to	19	completed	2026-06-15 13:36:42.925472+07	2026-06-15 13:36:42.925462+07	2026-06-15 13:37:32.624043+07	lifecycle:picking:confirmed	mqeubhn4nteoxmngcvi	A06
3256	517921cc	AGV02	go_to	19	completed	2026-06-17 14:26:19.290469+07	2026-06-17 14:26:19.290469+07	2026-06-17 14:26:21.587119+07		mqhqyzkaa3unckw0oin	A05
2872	2af362d6	AGV01	go_charge	\N	completed	2026-06-15 13:36:43.133014+07	2026-06-15 13:38:06.803427+07	2026-06-15 13:38:21.892261+07		mqeubhn4nteoxmngcvi	A06
2876	198a6a32	AGV02	go_to	17	completed	2026-06-15 13:36:49.558846+07	2026-06-15 13:38:13.834401+07	2026-06-15 13:39:14.132821+07	lifecycle:picking:confirmed	mqeubmr6iewmr0fqws	A06
2953	861f052a	AGV01	go_to	19	completed	2026-06-16 09:35:01.065842+07	2026-06-16 09:35:01.065834+07	2026-06-16 09:35:33.3115+07	lifecycle:picking:confirmed	mqg14iloc21p3h8ya4	A02
3077	f0f24500	AGV01	go_to	96	completed	2026-06-16 11:55:42.334571+07	2026-06-16 11:55:54.333718+07	2026-06-16 11:56:13.519745+07		mqg643a9yx8rzeckwg7	A05
2955	7b32b8d5	AGV01	go_to	18	completed	2026-06-16 09:35:01.230272+07	2026-06-16 09:37:43.931431+07	2026-06-16 09:37:58.515323+07		mqg14iloc21p3h8ya4	A02
3008	39f400cd	AGV02	go_to	19	completed	2026-06-16 10:41:53.894118+07	2026-06-16 10:41:53.894108+07	2026-06-16 10:42:06.046903+07		mqg3iixvmxwiizjkz9	A06
3010	8ab84d71	AGV02	go_to	16	completed	2026-06-16 10:41:53.914328+07	2026-06-16 10:42:47.816234+07	2026-06-16 10:43:05.496571+07		mqg3iixvmxwiizjkz9	A06
3006	7aefc952	AGV01	go_to	16	completed	2026-06-16 10:41:45.703564+07	2026-06-16 10:42:17.263837+07	2026-06-16 10:43:20.823604+07	lifecycle:picking:confirmed	mqg3ichgv8wg7olmg0n	A06
3080	80c8c85e	AGV01	go_to	9	completed	2026-06-16 11:56:29.681896+07	2026-06-16 11:56:29.682462+07	2026-06-16 11:56:42.926496+07		mqg643a9yx8rzeckwg7	A05
3014	b6f4bfd7	AGV02	go_to	16	completed	2026-06-16 10:43:05.504832+07	2026-06-16 10:43:25.167465+07	2026-06-16 10:44:45.28664+07	lifecycle:picking:confirmed	mqg3iixvmxwiizjkz9	A06
3015	0446361f	AGV01	go_charge	\N	completed	2026-06-16 10:43:20.852479+07	2026-06-16 10:43:35.748584+07	2026-06-16 10:44:51.929362+07	charge_arrived	mqg3ichgv8wg7olmg0n	A06
3207	d32cb714	AGV02	go_to	19	completed	2026-06-16 16:15:11.910542+07	2026-06-16 16:15:39.07084+07	2026-06-16 16:16:07.551547+07	lifecycle:picking:confirmed	mqgff5fpn74uc400zj	A02
3018	cada58ca	AGV01	go_to	17	completed	2026-06-16 10:48:07.532842+07	2026-06-16 10:48:43.182836+07	2026-06-16 10:49:05.62214+07	lifecycle:picking:confirmed	mqg3qj4r96h1k4wlry	A02
3082	74fa5504	AGV01	go_to	9	completed	2026-06-16 11:58:43.001645+07	2026-06-16 11:58:43.004032+07	2026-06-16 11:58:58.932923+07	off_route	mqg643a9yx8rzeckwg7	A05
3023	fdeeee2f	AGV02	go_to	16	completed	2026-06-16 10:48:25.945155+07	2026-06-16 10:49:11.413442+07	2026-06-16 10:50:58.214734+07	event:continue	mqg3qxf0a9s02v2wlwc	A02
3028	3686d1c5	AGV02	go_to	18	completed	2026-06-16 10:50:58.24226+07	2026-06-16 10:51:12.375442+07	2026-06-16 11:02:24.989243+07	lifecycle:picking:confirmed	mqg3qxf0a9s02v2wlwc	A02
3073	f2bc03a9	AGV02	go_to	19	completed	2026-06-16 11:54:49.551104+07	2026-06-16 11:54:49.551097+07	2026-06-16 11:59:00.491354+07	event:continue	mqg64b5om3fq6munei	A02
3025	91463238	AGV02	go_charge	\N	completed	2026-06-16 10:48:25.949023+07	2026-06-16 11:02:24.989338+07	2026-06-16 11:03:10.217004+07	charge_arrived	mqg3qxf0a9s02v2wlwc	A02
3201	3d4ae912	AGV01	go_to	16	completed	2026-06-16 16:14:56.169038+07	2026-06-16 16:15:56.827208+07	2026-06-16 16:16:31.83955+07	lifecycle:picking:confirmed	mqgfetauzd1yuo6yb89	A05
3026	133c176d	AGV02	go_to	19	running	2026-06-16 10:48:29.690537+07	2026-06-16 11:03:10.217645+07	\N		mqg3qxf0a9s02v2wlwc	dest_retry
3075	15049bf9	AGV02	go_to	15	completed	2026-06-16 11:54:49.566832+07	2026-06-16 11:59:28.258485+07	2026-06-16 11:59:43.021488+07		mqg64b5om3fq6munei	A02
3085	f2ddc0cb	AGV01	go_to	9	cancelled	2026-06-16 11:58:58.993067+07	\N	2026-06-16 13:11:26.29116+07	cancelled by user	mqg643a9yx8rzeckwg7	A05
3072	46873373	AGV01	go_to	69	cancelled	2026-06-16 11:54:39.362773+07	\N	2026-06-16 13:11:26.29116+07	cancelled by user	mqg643a9yx8rzeckwg7	A05
3079	11207d66	AGV01	go_to	96	cancelled	2026-06-16 11:56:13.652639+07	\N	2026-06-16 13:11:26.29116+07	cancelled by user	mqg643a9yx8rzeckwg7	A05
3127	10b02af0	AGV01	go_to	9	cancelled	2026-06-16 14:06:12.05019+07	2026-06-16 14:06:26.579791+07	2026-06-16 14:09:29.433384+07	force-cancelled by user	mqgareo2r995j36a5q	A05
3190	3ea80fd5	AGV02	go_charge	14	completed	2026-06-16 16:08:11.621692+07	2026-06-16 16:08:11.623681+07	2026-06-16 16:08:24.669884+07	off_route	mqgf1dkeaiwatba55uo	A02
3200	f7e2d1b0	AGV01	go_to	19	completed	2026-06-16 16:14:56.132974+07	2026-06-16 16:14:56.132974+07	2026-06-16 16:15:33.591941+07	lifecycle:picking:confirmed	mqgfetauzd1yuo6yb89	A05
3325	24e28171	AGV02	go_to	15	completed	2026-06-17 15:28:53.430733+07	2026-06-17 15:28:53.430733+07	2026-06-17 15:29:00.822588+07	parked_siding	mqht1i431tvwdr671ixh	yield_siding
3204	2e1cb2e1	AGV01	go_to	18	completed	2026-06-16 16:14:56.175041+07	2026-06-16 16:16:47.314482+07	2026-06-16 16:17:21.7788+07	lifecycle:picking:confirmed	mqgfetauzd1yuo6yb89	A05
3212	93e1d447	AGV02	go_to	15	completed	2026-06-16 16:16:58.203328+07	2026-06-16 16:16:58.203328+07	2026-06-16 16:17:23.868823+07	lifecycle:picking:confirmed	mqgff5fpn74uc400zj	dest_retry
3263	95e952ee	AGV02	go_to	19	completed	2026-06-17 14:26:21.601818+07	2026-06-17 14:26:45.25314+07	2026-06-17 14:27:18.23743+07	event:continue	mqhqyzkaa3unckw0oin	A05
3260	c3cb28b8	AGV02	go_to	17	cancelled	2026-06-17 14:26:19.341109+07	2026-06-17 14:29:41.895958+07	2026-06-17 14:37:55.147802+07	force-cancelled by user	mqhqyzkaa3unckw0oin	A05
3213	196b2b0c	AGV01	go_charge	\N	completed	2026-06-16 16:17:21.798636+07	2026-06-16 16:17:37.070483+07	2026-06-16 16:18:26.765078+07	charge_arrived	mqgfetauzd1yuo6yb89	A05
3210	c5862514	AGV02	go_charge	\N	completed	2026-06-16 16:15:11.939735+07	2026-06-16 16:17:23.887263+07	2026-06-16 16:19:00.825023+07	charge_arrived	mqgff5fpn74uc400zj	A02
3258	a69a7879	AGV02	go_to	16	completed	2026-06-17 14:26:19.333259+07	2026-06-17 14:27:18.23743+07	2026-06-17 14:27:34.961341+07		mqhqyzkaa3unckw0oin	A05
3255	f1580df0	AGV01	go_to	17	completed	2026-06-17 14:25:57.197578+07	2026-06-17 14:28:15.427613+07	2026-06-17 14:28:30.434908+07		mqhqyibpsjmtqtixyk	A05
3324	0bb6e8da	AGV02	go_to	18	completed	2026-06-17 15:28:37.182472+07	2026-06-17 15:28:49.740475+07	2026-06-17 15:28:53.429728+07	yield_siding	mqht1i431tvwdr671ixh	A05
3359	28d506eb	AGV01	go_to	17	completed	2026-06-17 16:05:02.861035+07	2026-06-17 16:05:39.585972+07	2026-06-17 16:06:14.324025+07	event:continue	mqhuhy6aq5oqwhj80ab	A05
3364	c13b895c	AGV02	go_to	19	completed	2026-06-17 16:05:25.436398+07	2026-06-17 16:05:27.72684+07	2026-06-17 16:05:49.396987+07		mqhuifm91ep4iqf2s27	A05
3366	c90eecdd	AGV02	go_to	18	completed	2026-06-17 16:05:25.474744+07	2026-06-17 16:08:13.534802+07	2026-06-17 16:08:28.240607+07		mqhuifm91ep4iqf2s27	A05
3373	7b02df25	AGV02	go_to	8	completed	2026-06-17 16:08:13.555802+07	2026-06-17 16:08:28.241612+07	2026-06-17 16:08:28.244611+07	already_at_dest	mqhuifm91ep4iqf2s27	A05
3376	46b9cc09	AGV02	go_to	18	completed	2026-06-17 16:09:28.437215+07	2026-06-17 16:09:28.43856+07	2026-06-17 16:11:27.395016+07	event:continue	mqhuifm91ep4iqf2s27	yield_resume
3369	36c3e3b8	AGV02	go_charge	\N	cancelled	2026-06-17 16:05:25.47916+07	\N	2026-06-17 16:15:37.953392+07	cancelled by user	mqhuifm91ep4iqf2s27	A05
3377	0882a516	AGV02	go_to	17	completed	2026-06-17 16:11:27.420543+07	2026-06-17 16:11:42.262327+07	2026-06-17 16:11:59.300735+07	lifecycle:picking:confirmed	mqhuifm91ep4iqf2s27	A05
3584	87712756	AGV01	go_to	18	completed	2026-07-08 14:45:32.670211+07	2026-07-08 14:46:09.877474+07	2026-07-08 14:46:23.451665+07	hook_raised	\N	\N
2247	63a662da	AGV01	go_to	19	cancelled	2026-06-08 15:16:09.615546+07	\N	2026-06-08 15:19:09.796871+07	cancelled by user	mq4xs4n3dp5uqazu50d	A06
2252	84bcf449	AGV02	go_to	19	completed	2026-06-08 15:27:31.450849+07	2026-06-08 15:27:31.450849+07	2026-06-08 15:27:44.487+07		mq4y710xzsd90oq16n	A06
2282	4e06e53b	AGV02	go_charge	\N	completed	2026-06-08 15:45:44.652048+07	2026-06-08 15:45:44.652048+07	2026-06-08 15:46:01.742055+07		mq4yugk4w8pe8bclxye	Sạc Pin
2249	39938054	AGV01	go_to	19	completed	2026-06-08 15:27:17.857769+07	2026-06-08 15:27:17.857769+07	2026-06-08 15:27:53.136077+07	lifecycle:picking:confirmed	mq4y6qfmay6du1si8d5	A06
2253	e9363f2f	AGV02	go_to	19	completed	2026-06-08 15:27:31.645229+07	2026-06-08 15:27:44.488017+07	2026-06-08 15:28:04.719241+07		mq4y710xzsd90oq16n	A06
2267	439ac0de	AGV01	go_charge	\N	cancelled	2026-06-08 15:32:12.778658+07	2026-06-08 15:32:33.935668+07	2026-06-08 15:37:44.230514+07	force-cancelled by user	mq4ybrvet3evzthnbb	A06
2256	80e2ccd9	AGV02	go_to	19	completed	2026-06-08 15:27:44.631465+07	2026-06-08 15:28:04.72724+07	2026-06-08 15:28:22.972678+07	lifecycle:picking:confirmed	mq4y710xzsd90oq16n	A06
2266	b41a0311	AGV02	go_charge	\N	completed	2026-06-08 15:31:29.186406+07	2026-06-08 15:37:32.534224+07	2026-06-08 15:37:47.685377+07		mq4yc4g993p775ev6q9	A06
2251	b022a45e	AGV01	go_to	17	completed	2026-06-08 15:27:18.03481+07	2026-06-08 15:27:53.136077+07	2026-06-08 15:28:24.938677+07	lifecycle:picking:confirmed	mq4y6qfmay6du1si8d5	A06
2287	5f267eab	AGV01	go_to	19	completed	2026-06-08 15:48:11.073037+07	2026-06-08 15:48:11.073037+07	2026-06-08 15:48:48.277993+07	lifecycle:picking:confirmed	mq4yxlgye5x2hnwkbhh	A06
2254	0d9f4483	AGV02	go_to	17	completed	2026-06-08 15:27:31.826239+07	2026-06-08 15:28:22.972678+07	2026-06-08 15:28:39.87859+07		mq4y710xzsd90oq16n	A06
2250	e8efd155	AGV01	go_charge	\N	completed	2026-06-08 15:27:18.035805+07	2026-06-08 15:28:24.943091+07	2026-06-08 15:28:40.998778+07		mq4y6qfmay6du1si8d5	A06
2271	18851c67	AGV02	go_charge	\N	completed	2026-06-08 15:37:32.69694+07	2026-06-08 15:37:47.687375+07	2026-06-08 15:38:37.435843+07	charge_arrived	mq4yc4g993p775ev6q9	A06
2272	41e325d7	AGV01	go_charge	\N	completed	2026-06-08 15:37:52.347805+07	2026-06-08 15:37:52.347805+07	2026-06-08 15:40:06.12272+07	charge_arrived	mq4ykc41yzp3x4f0ljs	Sạc Pin
2257	0c568a93	AGV02	go_to	17	completed	2026-06-08 15:28:22.986882+07	2026-06-08 15:28:39.879587+07	2026-06-08 15:29:49.143567+07	lifecycle:picking:confirmed	mq4y710xzsd90oq16n	A06
2258	a5a4f43c	AGV01	go_charge	\N	completed	2026-06-08 15:28:25.203738+07	2026-06-08 15:28:40.999762+07	2026-06-08 15:29:51.129611+07	charge_arrived	mq4y6qfmay6du1si8d5	A06
2255	67e23d1b	AGV02	go_charge	\N	completed	2026-06-08 15:27:31.831253+07	2026-06-08 15:29:49.144567+07	2026-06-08 15:30:05.596214+07	off_route	mq4y710xzsd90oq16n	A06
2259	d30fe47a	AGV02	go_charge	14	completed	2026-06-08 15:30:05.592107+07	2026-06-08 15:30:05.598215+07	2026-06-08 15:30:46.630169+07	charge_arrived	mq4y710xzsd90oq16n	A06
2260	20dff61b	AGV01	go_to	19	completed	2026-06-08 15:31:12.87983+07	2026-06-08 15:31:12.87983+07	2026-06-08 15:31:46.709339+07	lifecycle:picking:confirmed	mq4ybrvet3evzthnbb	A06
2263	fb449719	AGV02	go_to	19	completed	2026-06-08 15:31:29.148858+07	2026-06-08 15:31:29.148858+07	2026-06-08 15:31:56.495265+07		mq4yc4g993p775ev6q9	A06
2261	9b5d3c45	AGV01	go_to	17	completed	2026-06-08 15:31:12.898831+07	2026-06-08 15:31:46.709339+07	2026-06-08 15:32:12.684684+07	lifecycle:picking:confirmed	mq4ybrvet3evzthnbb	A06
2264	79c69551	AGV02	go_to	19	completed	2026-06-08 15:31:29.156406+07	2026-06-08 15:31:56.496268+07	2026-06-08 15:32:20.451736+07	lifecycle:picking:confirmed	mq4yc4g993p775ev6q9	A06
2262	09d8b782	AGV01	go_charge	\N	completed	2026-06-08 15:31:12.90083+07	2026-06-08 15:32:12.693695+07	2026-06-08 15:32:33.933656+07		mq4ybrvet3evzthnbb	A06
2284	7dbe550f	AGV01	go_charge	\N	cancelled	2026-06-08 15:45:54.37249+07	2026-06-08 15:45:54.37249+07	2026-06-08 15:46:19.860488+07	force-cancelled by user	mq4yuo2d0ncvmcai74fb	Sạc Pin
2265	aa749067	AGV02	go_to	17	completed	2026-06-08 15:31:29.185408+07	2026-06-08 15:32:20.451736+07	2026-06-08 15:32:37.331269+07		mq4yc4g993p775ev6q9	A06
2268	0093f11b	AGV02	go_to	17	completed	2026-06-08 15:32:20.487449+07	2026-06-08 15:32:37.345285+07	2026-06-08 15:37:08.503633+07	off_route	mq4yc4g993p775ev6q9	A06
2270	64564621	AGV02	go_to	19	completed	2026-06-08 15:37:08.499736+07	2026-06-08 15:37:08.507726+07	2026-06-08 15:37:08.520589+07	pickup_already_done	mq4yc4g993p775ev6q9	A06
2276	25e03d40	AGV02	go_to	19	completed	2026-06-08 15:42:50.620798+07	2026-06-08 15:42:50.620798+07	2026-06-08 15:43:03.324198+07		mq4yqq9k9mdhs2he2ev	A06
2269	49dd90f9	AGV02	go_to	17	completed	2026-06-08 15:32:37.38436+07	2026-06-08 15:37:08.526565+07	2026-06-08 15:37:32.533222+07	lifecycle:picking:confirmed	mq4yc4g993p775ev6q9	A06
2273	6418c4e6	AGV01	go_to	19	completed	2026-06-08 15:42:34.913721+07	2026-06-08 15:42:34.913721+07	2026-06-08 15:43:08.245382+07	lifecycle:picking:confirmed	mq4yqe28d33kv0ojs7	A06
2277	0f7a5ea6	AGV02	go_to	19	completed	2026-06-08 15:42:50.626812+07	2026-06-08 15:43:03.325346+07	2026-06-08 15:43:25.120145+07		mq4yqq9k9mdhs2he2ev	A06
2283	fcf54954	AGV02	go_charge	\N	completed	2026-06-08 15:45:44.682215+07	2026-06-08 15:46:01.74406+07	2026-06-08 15:46:35.646986+07	charge_arrived	mq4yugk4w8pe8bclxye	Sạc Pin
2274	e7f71160	AGV01	go_to	17	completed	2026-06-08 15:42:35.244492+07	2026-06-08 15:43:08.245382+07	2026-06-08 15:43:30.765477+07	lifecycle:picking:confirmed	mq4yqe28d33kv0ojs7	A06
2285	e04931a6	AGV01	go_charge	\N	completed	2026-06-08 15:46:25.173919+07	2026-06-08 15:46:25.173919+07	2026-06-08 15:46:40.394129+07		mq4yvbtu9mtu74sg2ag	Sạc Pin
2280	dc5bf403	AGV02	go_to	19	completed	2026-06-08 15:43:03.482476+07	2026-06-08 15:43:25.126216+07	2026-06-08 15:43:41.862746+07	lifecycle:picking:confirmed	mq4yqq9k9mdhs2he2ev	A06
2289	80751e04	AGV01	go_charge	\N	completed	2026-06-08 15:48:11.316445+07	2026-06-08 15:50:07.880937+07	2026-06-08 15:50:23.774027+07		mq4yxlgye5x2hnwkbhh	A06
2275	d1013a9f	AGV01	go_charge	\N	completed	2026-06-08 15:42:35.249117+07	2026-06-08 15:43:30.766461+07	2026-06-08 15:43:46.596149+07		mq4yqe28d33kv0ojs7	A06
2286	da338364	AGV01	go_charge	\N	completed	2026-06-08 15:46:25.193188+07	2026-06-08 15:46:40.396135+07	2026-06-08 15:47:41.247397+07	charge_arrived	mq4yvbtu9mtu74sg2ag	Sạc Pin
2281	a8957a35	AGV01	go_charge	\N	cancelled	2026-06-08 15:43:30.784985+07	2026-06-08 15:43:46.597154+07	2026-06-08 15:45:27.124505+07	force-cancelled by user	mq4yqe28d33kv0ojs7	A06
2278	c48788d5	AGV02	go_to	17	cancelled	2026-06-08 15:42:50.685965+07	2026-06-08 15:43:41.862746+07	2026-06-08 15:45:31.953687+07	force-cancelled by user	mq4yqq9k9mdhs2he2ev	A06
2279	aa7e7f40	AGV02	go_charge	\N	cancelled	2026-06-08 15:42:50.686966+07	\N	2026-06-08 15:45:31.953687+07	cancelled by user	mq4yqq9k9mdhs2he2ev	A06
2290	c19816eb	AGV02	go_to	19	completed	2026-06-08 15:48:28.594216+07	2026-06-08 15:48:28.594216+07	2026-06-08 15:48:41.222525+07		mq4yxz1um8d7mc0nv3	A06
2296	e205e905	AGV02	go_to	19	completed	2026-06-08 15:49:28.33403+07	2026-06-08 15:49:28.33403+07	2026-06-08 15:50:02.556399+07	lifecycle:picking:confirmed	mq4yz955q7vaftum6c	A06
2291	80f22d3f	AGV02	go_to	19	completed	2026-06-08 15:48:28.603211+07	2026-06-08 15:48:41.223526+07	2026-06-08 15:48:48.305981+07	off_route	mq4yxz1um8d7mc0nv3	A06
2299	3a2f1dee	AGV01	go_charge	\N	completed	2026-06-08 15:50:07.903515+07	2026-06-08 15:50:23.774027+07	2026-06-08 15:51:18.230611+07	charge_arrived	mq4yxlgye5x2hnwkbhh	A06
2295	abcf852d	AGV02	go_to	2	failed	2026-06-08 15:48:48.30298+07	2026-06-08 15:48:48.30798+07	2026-06-08 15:48:48.350074+07	Không tìm được đường đi từ -528 -> 2	mq4yxz1um8d7mc0nv3	A06
2294	9297a0da	AGV02	go_to	19	completed	2026-06-08 15:48:41.354947+07	2026-06-08 15:50:02.556399+07	2026-06-08 15:50:02.560417+07	already_at_dest	mq4yxz1um8d7mc0nv3	A06
2288	08d2f0f2	AGV01	go_to	17	completed	2026-06-08 15:48:11.314446+07	2026-06-08 15:48:48.277993+07	2026-06-08 15:50:07.880937+07	lifecycle:picking:confirmed	mq4yxlgye5x2hnwkbhh	A06
2293	c47250ad	AGV02	go_charge	\N	completed	2026-06-08 15:48:28.626225+07	2026-06-08 15:51:17.4026+07	2026-06-08 15:51:32.096634+07		mq4yxz1um8d7mc0nv3	A06
2292	49420882	AGV02	go_to	16	completed	2026-06-08 15:48:28.623218+07	2026-06-08 15:50:02.561398+07	2026-06-08 15:51:17.4026+07	lifecycle:picking:confirmed	mq4yxz1um8d7mc0nv3	A06
2300	f9232161	AGV02	go_charge	\N	completed	2026-06-08 15:51:17.419604+07	2026-06-08 15:51:32.097665+07	2026-06-08 15:53:19.572921+07	charge_arrived	mq4yxz1um8d7mc0nv3	A06
2297	6b8ae724	AGV02	go_to	16	cancelled	2026-06-08 15:49:28.373922+07	2026-06-08 15:53:19.574908+07	2026-06-08 15:53:34.953055+07	force-cancelled by user	mq4yz955q7vaftum6c	A06
2298	7af649b4	AGV02	go_charge	\N	cancelled	2026-06-08 15:49:28.374925+07	\N	2026-06-08 15:53:34.953055+07	cancelled by user	mq4yz955q7vaftum6c	A06
2303	776e8193	AGV01	go_charge	\N	completed	2026-06-08 15:54:39.208826+07	2026-06-08 15:56:10.94586+07	2026-06-08 15:56:26.806197+07		mq4z5wzsrly5als6qsp	A06
2313	c69ab41e	AGV02	go_to	19	completed	2026-06-08 15:59:12.019812+07	2026-06-08 15:59:12.021809+07	2026-06-08 15:59:12.024821+07	pickup_already_done	mq4zb9gisy7knccou4	A06
2312	d74dd3f3	AGV02	go_charge	\N	completed	2026-06-08 15:58:48.615991+07	2026-06-08 15:59:56.324048+07	2026-06-08 16:00:11.013791+07		mq4zb9gisy7knccou4	A06
2301	dda4bb6a	AGV01	go_to	19	completed	2026-06-08 15:54:39.161835+07	2026-06-08 15:54:39.161835+07	2026-06-08 15:55:12.925909+07	lifecycle:picking:confirmed	mq4z5wzsrly5als6qsp	A06
2304	a95b4eb6	AGV02	go_to	19	completed	2026-06-08 15:54:49.554608+07	2026-06-08 15:54:49.554608+07	2026-06-08 15:55:23.146719+07		mq4z6502e5tzcioavkd	A06
2305	71120c0b	AGV02	go_to	19	completed	2026-06-08 15:54:49.55961+07	2026-06-08 15:55:23.146719+07	2026-06-08 15:55:53.508115+07	lifecycle:picking:confirmed	mq4z6502e5tzcioavkd	A06
2307	b2d076be	AGV02	go_charge	\N	completed	2026-06-08 15:54:49.577126+07	2026-06-08 15:57:13.221388+07	2026-06-08 15:57:27.513158+07		mq4z6502e5tzcioavkd	A06
2806	b6073018	AGV02	go_to	19	completed	2026-06-15 11:13:15.379905+07	2026-06-15 11:13:15.379876+07	2026-06-15 11:13:46.167461+07		mqep701fccyw9me06sw	A06
2805	afeffa37	AGV01	go_to	17	completed	2026-06-15 11:13:03.926015+07	2026-06-15 11:13:34.847272+07	2026-06-15 11:14:09.165201+07	lifecycle:picking:confirmed	mqep6qo99u0kysy66rp	A06
2810	29e37f0b	AGV01	go_charge	\N	completed	2026-06-15 11:14:09.184339+07	2026-06-15 11:14:24.229785+07	2026-06-15 11:14:24.276708+07	yield_siding	mqep6qo99u0kysy66rp	A06
2812	aef338e5	AGV01	go_charge	\N	completed	2026-06-15 11:15:10.849371+07	2026-06-15 11:15:10.849349+07	2026-06-15 11:15:25.261253+07	off_route	mqep6qo99u0kysy66rp	yield_resume
2808	d7c69e50	AGV02	go_to	17	completed	2026-06-15 11:13:15.405177+07	2026-06-15 11:14:17.567417+07	2026-06-15 11:19:15.990579+07	lifecycle:picking:confirmed	mqep701fccyw9me06sw	A06
2816	524a0686	AGV02	go_charge	\N	completed	2026-06-15 11:19:16.010049+07	2026-06-15 11:19:30.471631+07	2026-06-15 11:20:17.43301+07	charge_arrived	mqep701fccyw9me06sw	A06
2874	15ff0976	AGV02	go_to	19	completed	2026-06-15 13:36:49.535879+07	2026-06-15 13:36:49.535874+07	2026-06-15 13:37:26.391087+07		mqeubmr6iewmr0fqws	A06
2875	8877cb25	AGV02	go_to	19	completed	2026-06-15 13:36:49.543235+07	2026-06-15 13:37:26.39288+07	2026-06-15 13:37:26.562774+07	dest_wait	mqeubmr6iewmr0fqws	A06
3129	dfe09fd9	AGV01	go_charge	\N	completed	2026-06-16 14:09:36.145069+07	2026-06-16 14:09:36.145047+07	2026-06-16 14:09:50.921542+07		mqgaxmv7tvrdzj73j8j	Sạc Pin
2873	ba57392e	AGV01	go_to	17	completed	2026-06-15 13:36:43.130156+07	2026-06-15 13:37:32.625219+07	2026-06-15 13:38:06.803299+07	lifecycle:picking:confirmed	mqeubhn4nteoxmngcvi	A06
2878	f7fea7c3	AGV02	go_to	19	completed	2026-06-15 13:37:39.985921+07	2026-06-15 13:37:39.985915+07	2026-06-15 13:38:13.834308+07	lifecycle:picking:confirmed	mqeubmr6iewmr0fqws	dest_retry
2877	fe323386	AGV02	go_charge	\N	completed	2026-06-15 13:36:49.559871+07	2026-06-15 13:39:14.132891+07	2026-06-15 13:39:28.612668+07		mqeubmr6iewmr0fqws	A06
2958	e72c62b9	AGV02	go_to	19	completed	2026-06-16 09:35:18.251881+07	2026-06-16 09:35:44.270304+07	2026-06-16 09:36:06.592238+07	off_route	mqg14vt8t650n3d0wp	A02
2880	bdf0fe9e	AGV02	go_charge	\N	completed	2026-06-15 13:39:14.146573+07	2026-06-15 13:39:28.613318+07	2026-06-15 13:40:20.570198+07	charge_arrived	mqeubmr6iewmr0fqws	A06
2884	9c962621	AGV02	go_to	19	completed	2026-06-15 13:43:50.032768+07	2026-06-15 13:43:50.032764+07	2026-06-15 13:44:22.963202+07		mqeukn7y2gbw9ud6gdr	A06
2954	729a1123	AGV01	go_to	16	completed	2026-06-16 09:35:01.226105+07	2026-06-16 09:35:33.311873+07	2026-06-16 09:37:43.931277+07	lifecycle:picking:confirmed	mqg14iloc21p3h8ya4	A02
2886	192a0857	AGV02	go_to	17	completed	2026-06-15 13:43:50.060155+07	2026-06-15 13:45:00.355802+07	2026-06-15 13:45:16.365338+07		mqeukn7y2gbw9ud6gdr	A06
2961	1292bd06	AGV02	go_charge	\N	completed	2026-06-16 09:35:18.423949+07	2026-06-16 09:38:24.917138+07	2026-06-16 09:39:32.056614+07	charge_arrived	mqg14vt8t650n3d0wp	A02
2883	3e2ebf63	AGV01	go_charge	\N	completed	2026-06-15 13:43:41.578584+07	2026-06-15 13:45:10.395399+07	2026-06-15 13:47:31.402546+07	charge_arrived	mqeukgmz4vidrj5mik8	A06
2890	0dfd66e7	AGV02	go_charge	\N	completed	2026-06-15 13:46:00.330052+07	2026-06-15 13:46:14.793388+07	2026-06-15 13:47:41.851455+07	charge_arrived	mqeukn7y2gbw9ud6gdr	A06
2903	eaf84f7b	AGV02	go_to	19	completed	2026-06-15 13:53:02.101518+07	2026-06-15 13:53:02.101507+07	2026-06-15 13:53:36.743372+07		mqeuwh6oeifpgss7nvv	A06
2901	db71e431	AGV01	go_to	17	completed	2026-06-15 13:52:51.203768+07	2026-06-15 13:53:27.700706+07	2026-06-15 13:53:55.806944+07	lifecycle:picking:confirmed	mqeuw8qifzw9xky6xr7	A06
3012	09e4d4ca	AGV02	go_to	19	completed	2026-06-16 10:42:06.195876+07	2026-06-16 10:42:27.159799+07	2026-06-16 10:42:47.816125+07	lifecycle:picking:confirmed	mqg3iixvmxwiizjkz9	A06
2902	3dd0572c	AGV01	go_charge	\N	completed	2026-06-15 13:52:51.216751+07	2026-06-15 13:53:55.807224+07	2026-06-15 13:54:15.060743+07		mqeuw8qifzw9xky6xr7	A06
2905	194cf1c1	AGV02	go_to	17	completed	2026-06-15 13:53:02.134448+07	2026-06-15 13:54:07.961419+07	2026-06-15 13:54:58.905461+07	lifecycle:picking:confirmed	mqeuwh6oeifpgss7nvv	A06
2908	e641bdf5	AGV02	go_charge	\N	completed	2026-06-15 13:54:58.972961+07	2026-06-15 13:55:13.51522+07	2026-06-15 13:55:35.125497+07	charge_arrived	mqeuwh6oeifpgss7nvv	A06
3013	a8512ee1	AGV02	go_to	16	completed	2026-06-16 10:42:47.824647+07	2026-06-16 10:43:05.49746+07	2026-06-16 10:43:25.167069+07		mqg3iixvmxwiizjkz9	A06
3017	5005772e	AGV01	go_to	19	completed	2026-06-16 10:48:07.499026+07	2026-06-16 10:48:07.499012+07	2026-06-16 10:48:43.18267+07	lifecycle:picking:confirmed	mqg3qj4r96h1k4wlry	A02
3192	6f67c370	AGV02	go_to	2	completed	2026-06-16 16:08:24.668521+07	2026-06-16 16:08:24.669884+07	2026-06-16 16:08:33.468825+07	off_route	mqgf1dkeaiwatba55uo	A02
3019	09bcabeb	AGV01	go_to	15	completed	2026-06-16 10:48:07.534908+07	2026-06-16 10:49:05.622218+07	2026-06-16 10:49:20.891193+07		mqg3qj4r96h1k4wlry	A02
3331	bef774c0	AGV01	go_to	4	completed	2026-06-17 15:37:20.365727+07	2026-06-17 15:37:20.366728+07	2026-06-17 15:37:34.733867+07	off_route	mqhti3hmhclorilf5sd	Sạc Pin
3027	28ca3c55	AGV01	go_to	15	completed	2026-06-16 10:49:05.642295+07	2026-06-16 10:49:20.892651+07	2026-06-16 10:50:03.014325+07	lifecycle:picking:confirmed	mqg3qj4r96h1k4wlry	A02
3194	d3c3c413	AGV02	go_to	1	completed	2026-06-16 16:08:33.467825+07	2026-06-16 16:08:33.468825+07	2026-06-16 16:09:18.555561+07	off_route	mqgf1dkeaiwatba55uo	A02
3024	4a179a34	AGV02	go_to	18	completed	2026-06-16 10:48:25.947415+07	2026-06-16 10:50:58.21586+07	2026-06-16 10:51:12.374821+07		mqg3qxf0a9s02v2wlwc	A02
3081	ba6b5f45	AGV01	go_to	9	completed	2026-06-16 11:56:29.758131+07	2026-06-16 11:56:42.927238+07	2026-06-16 11:58:43.00264+07	off_route	mqg643a9yx8rzeckwg7	A05
3197	2df3573f	AGV02	go_to	96	cancelled	2026-06-16 16:09:18.58315+07	\N	2026-06-16 16:12:57.774038+07	cancelled by user	mqgf1dkeaiwatba55uo	A02
3087	68da7ead	AGV01	go_to	15	cancelled	2026-06-16 11:59:14.101301+07	2026-06-16 11:59:33.625525+07	2026-06-16 13:11:26.288594+07	force-cancelled by user	mqg643a9yx8rzeckwg7	A05
3193	6fc62e51	AGV02	go_to	2	cancelled	2026-06-16 16:08:24.689762+07	\N	2026-06-16 16:12:57.774038+07	cancelled by user	mqgf1dkeaiwatba55uo	A02
3191	360ead89	AGV02	go_charge	\N	cancelled	2026-06-16 16:08:11.746661+07	\N	2026-06-16 16:12:57.774038+07	cancelled by user	mqgf1dkeaiwatba55uo	A02
3269	260e0751	AGV02	go_charge	\N	cancelled	2026-06-17 14:38:05.885919+07	2026-06-17 14:38:05.885919+07	2026-06-17 14:38:19.511816+07	force-cancelled by user	mqhre4sxnybnkm2wvrd	Sạc Pin
3329	97e1b5cd	AGV01	go_charge	\N	completed	2026-06-17 15:37:10.06547+07	2026-06-17 15:37:10.06547+07	2026-06-17 15:37:20.366728+07	off_route	mqhti3hmhclorilf5sd	Sạc Pin
3365	08e46a5d	AGV02	go_to	16	completed	2026-06-17 16:05:25.472508+07	2026-06-17 16:07:28.812632+07	2026-06-17 16:08:13.534802+07	lifecycle:picking:confirmed	mqhuifm91ep4iqf2s27	A05
3362	1bf1ecb4	AGV01	go_to	18	completed	2026-06-17 16:05:02.864035+07	2026-06-17 16:07:37.965695+07	2026-06-17 16:08:17.58331+07	lifecycle:picking:confirmed	mqhuhy6aq5oqwhj80ab	A05
3335	c744720a	AGV01	go_to	4	completed	2026-06-17 15:37:34.902497+07	2026-06-17 15:37:50.019216+07	2026-06-17 15:38:30.889846+07	lifecycle:picking:confirmed	mqhti3hmhclorilf5sd	Sạc Pin
3363	a67cdf00	AGV02	go_to	19	completed	2026-06-17 16:05:25.427892+07	2026-06-17 16:05:25.427892+07	2026-06-17 16:05:27.725639+07		mqhuifm91ep4iqf2s27	A05
3371	cc744746	AGV01	go_to	15	completed	2026-06-17 16:06:14.350021+07	2026-06-17 16:06:31.956251+07	2026-06-17 16:07:37.965695+07	lifecycle:picking:confirmed	mqhuhy6aq5oqwhj80ab	A05
3374	3c31aac1	AGV02	go_to	15	completed	2026-06-17 16:08:31.944992+07	2026-06-17 16:08:31.944992+07	2026-06-17 16:08:39.474693+07	parked_siding	mqhuifm91ep4iqf2s27	yield_siding
3372	16cc2355	AGV02	go_to	18	completed	2026-06-17 16:08:13.541393+07	2026-06-17 16:08:28.245667+07	2026-06-17 16:08:31.943963+07	yield_siding	mqhuifm91ep4iqf2s27	A05
3368	42efc67b	AGV02	go_to	15	cancelled	2026-06-17 16:05:25.477741+07	2026-06-17 16:11:59.300735+07	2026-06-17 16:15:37.953392+07	force-cancelled by user	mqhuifm91ep4iqf2s27	A05
3421	c9f19bbc	AGV02	go_to	16	completed	2026-06-18 08:13:16.216587+07	2026-06-18 08:15:26.064883+07	2026-06-18 08:15:44.06545+07	off_route	mqit33af6cot1unb2zx	A05
3422	66ee6344	AGV01	go_to	18	completed	2026-06-18 08:14:10.961356+07	2026-06-18 08:14:26.102652+07	2026-06-18 08:14:47.400601+07		mqit2a1jo8v278sc1x	A05
3434	e72f10f5	AGV01	go_to	19	completed	2026-06-18 08:52:09.035999+07	2026-06-18 08:52:09.035999+07	2026-06-18 08:54:11.587632+07	event:continue	mqiuh3by2ycpfx3pkt2	A02
3435	947ca87e	AGV01	go_to	17	completed	2026-06-18 08:52:09.074012+07	2026-06-18 08:54:11.588678+07	2026-06-18 08:54:47.710281+07	event:continue	mqiuh3by2ycpfx3pkt2	A02
2341	7a502fdf	AGV01	go_to	19	completed	2026-06-08 16:19:09.24723+07	2026-06-08 16:19:09.24723+07	2026-06-08 16:19:50.718876+07	lifecycle:picking:confirmed	mq501fbnxczexpjxukp	A06
2302	d0447d2c	AGV01	go_to	17	completed	2026-06-08 15:54:39.204829+07	2026-06-08 15:55:12.925909+07	2026-06-08 15:56:10.943753+07	event:continue	mq4z5wzsrly5als6qsp	A06
2306	3247dced	AGV02	go_to	16	completed	2026-06-08 15:54:49.576129+07	2026-06-08 15:55:53.508115+07	2026-06-08 15:57:13.22039+07	lifecycle:picking:confirmed	mq4z6502e5tzcioavkd	A06
2308	285a6eaa	AGV01	go_charge	\N	completed	2026-06-08 15:56:10.983755+07	2026-06-08 15:56:26.807476+07	2026-06-08 15:57:21.197545+07	charge_arrived	mq4z5wzsrly5als6qsp	A06
2309	291b7df8	AGV02	go_charge	\N	completed	2026-06-08 15:57:13.236397+07	2026-06-08 15:57:27.513158+07	2026-06-08 15:58:39.28319+07	charge_arrived	mq4z6502e5tzcioavkd	A06
2310	8d43457c	AGV02	go_to	19	completed	2026-06-08 15:58:48.600879+07	2026-06-08 15:58:48.600879+07	2026-06-08 15:59:12.020811+07	off_route	mq4zb9gisy7knccou4	A06
2332	1964e9ce	AGV01	go_to	5	completed	2026-06-08 16:11:09.559307+07	2026-06-08 16:11:09.563482+07	2026-06-08 16:11:46.263202+07	off_route	mq4zo2b84n6gnqbr4d	A06
2311	471fbfed	AGV02	go_to	16	completed	2026-06-08 15:58:48.612992+07	2026-06-08 15:59:12.025817+07	2026-06-08 15:59:56.323058+07	event:continue	mq4zb9gisy7knccou4	A06
2351	242d8504	AGV01	go_charge	\N	completed	2026-06-08 16:25:51.505154+07	2026-06-08 16:28:03.743409+07	2026-06-08 16:28:19.590719+07		mq50a1o4q7dg55tdx2	A06
2314	0eddfb91	AGV02	go_charge	\N	completed	2026-06-08 15:59:56.336058+07	2026-06-08 16:00:11.014793+07	2026-06-08 16:01:23.746491+07	charge_arrived	mq4zb9gisy7knccou4	A06
2315	2ec4274b	AGV01	go_to	19	completed	2026-06-08 16:01:23.600817+07	2026-06-08 16:01:23.600817+07	2026-06-08 16:02:00.928574+07	event:continue	mq4zel16xntzumtqf4r	A06
2318	ff4b1dab	AGV02	go_to	19	completed	2026-06-08 16:01:33.74298+07	2026-06-08 16:01:33.74298+07	2026-06-08 16:02:06.96435+07		mq4zesvfhc1s59dujas	A06
2334	047710f5	AGV01	go_to	17	completed	2026-06-08 16:11:46.257702+07	2026-06-08 16:11:46.269467+07	2026-06-08 16:12:06.276397+07		mq4zo2b84n6gnqbr4d	A06
2348	7e90f741	AGV01	go_charge	\N	completed	2026-06-08 16:20:53.413191+07	2026-06-08 16:21:11.130617+07	2026-06-08 16:22:10.867597+07	charge_arrived	mq501fbnxczexpjxukp	A06
2319	1f4e51ad	AGV02	go_to	19	completed	2026-06-08 16:01:33.747978+07	2026-06-08 16:02:06.965352+07	2026-06-08 16:02:46.786842+07	lifecycle:picking:confirmed	mq4zesvfhc1s59dujas	A06
2316	5d5391c0	AGV01	go_to	17	completed	2026-06-08 16:01:23.637295+07	2026-06-08 16:02:00.92957+07	2026-06-08 16:02:52.548425+07	lifecycle:picking:confirmed	mq4zel16xntzumtqf4r	A06
2335	0f3cb8c2	AGV01	go_to	17	completed	2026-06-08 16:11:46.334216+07	2026-06-08 16:12:06.280617+07	2026-06-08 16:13:18.558042+07	lifecycle:picking:confirmed	mq4zo2b84n6gnqbr4d	A06
2317	f07007dc	AGV01	go_charge	\N	completed	2026-06-08 16:01:23.63931+07	2026-06-08 16:02:52.548425+07	2026-06-08 16:03:08.326373+07		mq4zel16xntzumtqf4r	A06
2344	2ee2b3a5	AGV02	go_to	19	completed	2026-06-08 16:19:18.86087+07	2026-06-08 16:19:18.86087+07	2026-06-08 16:19:52.932869+07		mq501mqiecrg3nhr2eb	A06
2321	d23f5e98	AGV02	go_to	16	completed	2026-06-08 16:01:33.763661+07	2026-06-08 16:02:46.786842+07	2026-06-08 16:03:59.15391+07	event:continue	mq4zesvfhc1s59dujas	A06
2329	b09dcf5c	AGV02	go_to	16	cancelled	2026-06-08 16:08:58.136836+07	2026-06-08 16:10:00.919165+07	2026-06-08 16:13:26.484622+07	force-cancelled by user	mq4zobrdxk01igdf6t	A06
2322	3d98ef49	AGV01	go_charge	\N	completed	2026-06-08 16:02:52.560552+07	2026-06-08 16:03:08.326373+07	2026-06-08 16:04:11.63225+07	charge_arrived	mq4zel16xntzumtqf4r	A06
2320	3cac0287	AGV02	go_charge	\N	completed	2026-06-08 16:01:33.76467+07	2026-06-08 16:03:59.157915+07	2026-06-08 16:04:13.924804+07		mq4zesvfhc1s59dujas	A06
2330	d5a652c0	AGV02	go_charge	\N	cancelled	2026-06-08 16:08:58.137835+07	\N	2026-06-08 16:13:26.495631+07	cancelled by user	mq4zobrdxk01igdf6t	A06
2323	b2118ab9	AGV02	go_charge	\N	completed	2026-06-08 16:03:59.229906+07	2026-06-08 16:04:13.94369+07	2026-06-08 16:05:24.903755+07	charge_arrived	mq4zesvfhc1s59dujas	A06
2324	84a22bdf	AGV01	go_to	19	completed	2026-06-08 16:08:45.878032+07	2026-06-08 16:08:45.878032+07	2026-06-08 16:09:23.242158+07	lifecycle:picking:confirmed	mq4zo2b84n6gnqbr4d	A06
2333	380e8bd7	AGV01	go_to	5	cancelled	2026-06-08 16:11:09.691587+07	2026-06-08 16:13:18.558042+07	2026-06-08 16:13:55.365317+07	force-cancelled by user	mq4zo2b84n6gnqbr4d	A06
2327	da870dc8	AGV02	go_to	19	completed	2026-06-08 16:08:58.117845+07	2026-06-08 16:08:58.117845+07	2026-06-08 16:09:30.595326+07		mq4zobrdxk01igdf6t	A06
2325	e5f6f0ce	AGV01	go_to	17	completed	2026-06-08 16:08:45.90814+07	2026-06-08 16:09:23.253436+07	2026-06-08 16:09:59.011403+07	lifecycle:picking:confirmed	mq4zo2b84n6gnqbr4d	A06
2349	4f8816be	AGV02	go_charge	\N	completed	2026-06-08 16:21:35.599968+07	2026-06-08 16:21:50.588159+07	2026-06-08 16:23:00.687688+07	charge_arrived	mq501mqiecrg3nhr2eb	A06
2328	71834bb3	AGV02	go_to	19	completed	2026-06-08 16:08:58.122828+07	2026-06-08 16:09:30.596347+07	2026-06-08 16:10:00.919165+07	lifecycle:picking:confirmed	mq4zobrdxk01igdf6t	A06
2345	c0c486ca	AGV02	go_to	19	completed	2026-06-08 16:19:18.864809+07	2026-06-08 16:19:52.933864+07	2026-06-08 16:20:46.766742+07	event:continue	mq501mqiecrg3nhr2eb	A06
2326	3e7a3fe0	AGV01	go_charge	\N	completed	2026-06-08 16:08:45.912036+07	2026-06-08 16:09:59.013398+07	2026-06-08 16:11:09.563482+07	off_route	mq4zo2b84n6gnqbr4d	A06
2331	0071efab	AGV01	go_charge	\N	cancelled	2026-06-08 16:09:59.045845+07	\N	2026-06-08 16:13:55.366363+07	cancelled by user	mq4zo2b84n6gnqbr4d	A06
2336	41421c8e	AGV02	go_charge	\N	completed	2026-06-08 16:13:35.676268+07	2026-06-08 16:13:35.676268+07	2026-06-08 16:14:50.243825+07	off_route	mq4zu9xmtdpdf94u39k	Sạc Pin
2342	5f77526a	AGV01	go_to	17	completed	2026-06-08 16:19:09.262215+07	2026-06-08 16:19:50.718876+07	2026-06-08 16:20:53.38305+07	event:continue	mq501fbnxczexpjxukp	A06
2337	7440f043	AGV01	go_charge	\N	cancelled	2026-06-08 16:14:41.080062+07	2026-06-08 16:14:41.080062+07	2026-06-08 16:15:02.173687+07	force-cancelled by user	mq4zvodl59dibxqck	Sạc Pin
2339	ee38759e	AGV01	go_charge	\N	completed	2026-06-08 16:15:14.597335+07	2026-06-08 16:15:14.597335+07	2026-06-08 16:15:30.315394+07		mq4zwe9onuhmwb9a0xl	Sạc Pin
2338	582bec16	AGV02	go_charge	14	cancelled	2026-06-08 16:14:50.243825+07	2026-06-08 16:14:50.243825+07	2026-06-08 16:15:31.506468+07	force-cancelled by user	mq4zu9xmtdpdf94u39k	Sạc Pin
2340	6cb0111b	AGV01	go_charge	\N	completed	2026-06-08 16:15:14.616089+07	2026-06-08 16:15:30.32039+07	2026-06-08 16:16:24.833324+07	charge_arrived	mq4zwe9onuhmwb9a0xl	Sạc Pin
2343	cdeccd1b	AGV01	go_charge	\N	completed	2026-06-08 16:19:09.264223+07	2026-06-08 16:20:53.38305+07	2026-06-08 16:21:11.130617+07		mq501fbnxczexpjxukp	A06
2350	f75f755a	AGV01	go_to	19	completed	2026-06-08 16:25:51.462614+07	2026-06-08 16:25:51.462614+07	2026-06-08 16:26:30.980642+07	lifecycle:picking:confirmed	mq50a1o4q7dg55tdx2	A06
2346	c3a6354b	AGV02	go_to	16	completed	2026-06-08 16:19:18.89083+07	2026-06-08 16:20:46.767754+07	2026-06-08 16:21:35.583926+07	event:continue	mq501mqiecrg3nhr2eb	A06
2347	4cf9e737	AGV02	go_charge	\N	completed	2026-06-08 16:19:18.894816+07	2026-06-08 16:21:35.58495+07	2026-06-08 16:21:50.582163+07		mq501mqiecrg3nhr2eb	A06
2811	2bc0372e	AGV01	go_to	16	completed	2026-06-15 11:14:24.278008+07	2026-06-15 11:14:24.278001+07	2026-06-15 11:15:09.704389+07	parked_siding	mqep6qo99u0kysy66rp	yield_siding
2358	1f5b410e	AGV02	go_to	17	completed	2026-06-08 16:26:24.063845+07	2026-06-08 16:27:12.704854+07	2026-06-08 16:27:29.620092+07		mq50aqsh20kqt7ebfyt	A06
2356	0acd7ce1	AGV02	go_to	19	completed	2026-06-08 16:26:24.039831+07	2026-06-08 16:26:24.039831+07	2026-06-08 16:26:45.428312+07		mq50aqsh20kqt7ebfyt	A06
2357	b5e17809	AGV02	go_to	19	completed	2026-06-08 16:26:24.044832+07	2026-06-08 16:26:45.428312+07	2026-06-08 16:27:12.704854+07	lifecycle:picking:confirmed	mq50aqsh20kqt7ebfyt	A06
2360	0620e04a	AGV02	go_to	17	completed	2026-06-08 16:27:12.719853+07	2026-06-08 16:27:29.621149+07	2026-06-08 16:27:48.385275+07		mq50aqsh20kqt7ebfyt	A06
2361	4dd08ac2	AGV02	go_to	17	completed	2026-06-08 16:27:29.635052+07	2026-06-08 16:27:48.386354+07	2026-06-08 16:27:48.39224+07	dest_wait	mq50aqsh20kqt7ebfyt	A06
2352	c840dc61	AGV01	go_to	17	completed	2026-06-08 16:25:51.503153+07	2026-06-08 16:26:30.980642+07	2026-06-08 16:28:03.738403+07	lifecycle:picking:confirmed	mq50a1o4q7dg55tdx2	A06
2365	03878b2f	AGV02	go_to	4	cancelled	2026-06-08 16:28:20.631746+07	\N	2026-06-08 16:29:18.752795+07	cancelled by user	mq50aqsh20kqt7ebfyt	A06
2359	54d72dd0	AGV02	go_charge	\N	completed	2026-06-08 16:26:24.065835+07	2026-06-08 16:27:48.393297+07	2026-06-08 16:28:20.609104+07	off_route	mq50aqsh20kqt7ebfyt	A06
2364	4659ff7f	AGV02	go_to	4	completed	2026-06-08 16:28:20.608096+07	2026-06-08 16:28:20.609104+07	2026-06-08 16:28:34.36105+07	off_route	mq50aqsh20kqt7ebfyt	A06
2353	d6895c85	AGV01	go_to	19	cancelled	2026-06-08 16:26:05.424122+07	\N	2026-06-08 16:29:28.64236+07	cancelled by user	mq50acehnmt7w92qkke	A06
2814	601ce7d7	AGV01	go_to	8	completed	2026-06-15 11:15:25.26069+07	2026-06-15 11:15:25.261659+07	2026-06-15 11:20:02.08377+07		mqep6qo99u0kysy66rp	yield_resume
2366	445d5219	AGV02	go_to	4	completed	2026-06-08 16:28:34.35967+07	2026-06-08 16:28:34.362065+07	2026-06-08 16:28:51.414928+07	off_route	mq50aqsh20kqt7ebfyt	A06
2368	3956ab42	AGV02	go_to	19	completed	2026-06-08 16:28:51.412926+07	2026-06-08 16:28:51.415931+07	2026-06-08 16:28:51.419927+07	pickup_already_done	mq50aqsh20kqt7ebfyt	A06
2367	ff52a7b2	AGV02	go_to	4	completed	2026-06-08 16:28:34.610606+07	2026-06-08 16:28:51.42193+07	2026-06-08 16:29:08.294555+07	off_route	mq50aqsh20kqt7ebfyt	A06
2371	19d8b3f0	AGV02	go_to	64	cancelled	2026-06-08 16:29:08.331552+07	\N	2026-06-08 16:29:18.752795+07	cancelled by user	mq50aqsh20kqt7ebfyt	A06
2362	bc3a28c9	AGV02	go_charge	\N	cancelled	2026-06-08 16:27:48.415239+07	\N	2026-06-08 16:29:18.752795+07	cancelled by user	mq50aqsh20kqt7ebfyt	A06
2363	02927cb9	AGV01	go_charge	\N	cancelled	2026-06-08 16:28:03.79143+07	2026-06-08 16:28:19.591616+07	2026-06-08 16:29:28.64236+07	force-cancelled by user	mq50a1o4q7dg55tdx2	A06
3033	ced8f235	AGV01	go_charge	\N	completed	2026-06-16 11:10:01.828216+07	2026-06-16 11:26:01.423236+07	2026-06-16 11:26:58.036653+07	off_route	mqg4ip6rvwvjk57emj	A05
2815	6a5cb704	AGV01	go_to	8	completed	2026-06-15 11:15:25.331411+07	2026-06-15 11:20:02.084851+07	2026-06-15 11:20:29.358754+07	lifecycle:picking:confirmed	mqep6qo99u0kysy66rp	yield_resume
2879	48a69d99	AGV01	go_charge	\N	completed	2026-06-15 13:38:06.827411+07	2026-06-15 13:38:21.892648+07	2026-06-15 13:39:51.894411+07	charge_arrived	mqeubhn4nteoxmngcvi	A06
2885	3385bb56	AGV02	go_to	19	completed	2026-06-15 13:43:50.037924+07	2026-06-15 13:44:22.966012+07	2026-06-15 13:44:22.975114+07	dest_wait	mqeukn7y2gbw9ud6gdr	A06
2881	2eb7862b	AGV01	go_to	19	completed	2026-06-15 13:43:41.555421+07	2026-06-15 13:43:41.555414+07	2026-06-15 13:44:31.346046+07	lifecycle:picking:confirmed	mqeukgmz4vidrj5mik8	A06
3090	459787a5	AGV01	go_charge	\N	cancelled	2026-06-16 13:11:46.169817+07	2026-06-16 13:11:46.169798+07	2026-06-16 13:12:09.630044+07	force-cancelled by user	mqg8v9f7p7j7okwhw4i	Sạc Pin
2882	7acfde13	AGV01	go_to	17	completed	2026-06-15 13:43:41.577968+07	2026-06-15 13:44:31.346119+07	2026-06-15 13:45:10.395335+07	lifecycle:picking:confirmed	mqeukgmz4vidrj5mik8	A06
3091	145d1147	AGV02	go_charge	\N	cancelled	2026-06-16 13:12:07.578603+07	2026-06-16 13:12:07.5786+07	2026-06-16 13:12:23.05849+07	force-cancelled by user	mqg8vpylqjexkeu1nj	Sạc Pin
2889	b0128291	AGV02	go_to	17	completed	2026-06-15 13:45:00.364026+07	2026-06-15 13:45:16.36607+07	2026-06-15 13:46:00.316028+07	lifecycle:picking:confirmed	mqeukn7y2gbw9ud6gdr	A06
2887	a9d326b9	AGV02	go_charge	\N	completed	2026-06-15 13:43:50.061847+07	2026-06-15 13:46:00.31613+07	2026-06-15 13:46:14.792688+07		mqeukn7y2gbw9ud6gdr	A06
3378	fb1c8ae5	AGV01	go_charge	\N	completed	2026-06-17 16:15:47.984866+07	2026-06-17 16:15:47.984866+07	2026-06-17 16:16:49.636703+07	charge_arrived	mqhuvs0h0uy7acxkdyx	Sạc Pin
3093	4dc8345d	AGV02	go_charge	\N	completed	2026-06-16 13:12:29.641349+07	2026-06-16 13:12:44.001829+07	2026-06-16 13:13:28.003144+07	charge_arrived	mqg8w6yzewf57vqu4r5	Sạc Pin
2895	cee7e5fb	AGV02	go_to	19	completed	2026-06-15 13:48:49.036019+07	2026-06-15 13:49:24.559575+07	2026-06-15 13:49:49.642153+07	lifecycle:picking:confirmed	mqeur1xr0aafme4lhyd	A06
2892	f8cb4ff4	AGV01	go_to	17	completed	2026-06-15 13:48:41.225116+07	2026-06-15 13:49:13.786655+07	2026-06-15 13:49:59.498688+07	lifecycle:picking:confirmed	mqeuqvwgx5hgrclan	A06
2896	158210ee	AGV02	go_to	17	completed	2026-06-15 13:48:49.058723+07	2026-06-15 13:49:49.642271+07	2026-06-15 13:50:05.642408+07		mqeur1xr0aafme4lhyd	A06
2957	82fd8beb	AGV02	go_to	19	completed	2026-06-16 09:35:18.1796+07	2026-06-16 09:35:18.179584+07	2026-06-16 09:35:44.269347+07		mqg14vt8t650n3d0wp	A02
2962	6d6a0c92	AGV02	go_to	19	queued	2026-06-16 09:36:06.59184+07	\N	\N	\N	mqg14vt8t650n3d0wp	A02
3156	a4ff5822	AGV01	go_to	69	completed	2026-06-16 14:22:47.033475+07	2026-06-16 14:23:00.922492+07	2026-06-16 14:23:36.694987+07	event:continue	mqgb53r3i1fjyn17vf	A05
2959	d7dacca1	AGV02	go_to	17	completed	2026-06-16 09:35:18.409514+07	2026-06-16 09:36:06.59531+07	2026-06-16 09:36:24.757345+07		mqg14vt8t650n3d0wp	A02
3130	aed6d175	AGV01	go_charge	\N	completed	2026-06-16 14:09:36.16774+07	2026-06-16 14:09:50.921958+07	2026-06-16 14:10:04.985653+07	off_route	mqgaxmv7tvrdzj73j8j	Sạc Pin
2960	dbf1c65a	AGV02	go_to	15	completed	2026-06-16 09:35:18.416983+07	2026-06-16 09:37:39.994252+07	2026-06-16 09:38:24.916879+07	event:continue	mqg14vt8t650n3d0wp	A02
2956	5eeb9e0b	AGV01	go_charge	\N	completed	2026-06-16 09:35:01.233934+07	2026-06-16 09:39:03.265371+07	2026-06-16 09:39:21.638689+07	charge_arrived	mqg14iloc21p3h8ya4	A02
3029	7f4a6166	AGV01	go_to	64	completed	2026-06-16 11:10:01.638882+07	2026-06-16 11:10:01.638876+07	2026-06-16 11:10:37.544084+07	lifecycle:picking:confirmed	mqg4ip6rvwvjk57emj	A05
3030	01868450	AGV01	go_to	96	completed	2026-06-16 11:10:01.804417+07	2026-06-16 11:12:30.970966+07	2026-06-16 11:12:42.937278+07		mqg4ip6rvwvjk57emj	A05
3044	6a307347	AGV01	go_to	9	completed	2026-06-16 11:13:21.136354+07	2026-06-16 11:13:34.228877+07	2026-06-16 11:16:52.818877+07	event:continue	mqg4ip6rvwvjk57emj	A05
3045	a42c902c	AGV02	go_charge	\N	completed	2026-06-16 11:15:52.860149+07	2026-06-16 11:16:07.05478+07	2026-06-16 11:17:10.004106+07	charge_arrived	mqg4j0j3qqi1ob33vfc	A02
3379	df72ad1b	AGV02	go_charge	\N	completed	2026-06-17 16:15:57.62461+07	2026-06-17 16:15:57.62461+07	2026-06-17 16:17:07.300777+07	charge_arrived	mqhuvzgc0tgp2px5ecfb	Sạc Pin
3134	c2a9af59	AGV01	go_to	64	completed	2026-06-16 14:15:24.637066+07	2026-06-16 14:15:24.637045+07	2026-06-16 14:16:04.922064+07	lifecycle:picking:confirmed	mqgb53r3i1fjyn17vf	A05
3138	19415b9c	AGV01	go_to	15	completed	2026-06-16 14:15:24.672415+07	2026-06-16 14:24:44.793694+07	2026-06-16 14:25:18.012219+07	lifecycle:picking:confirmed	mqgb53r3i1fjyn17vf	A05
3136	7344bf02	AGV01	go_to	96	completed	2026-06-16 14:15:24.664262+07	2026-06-16 14:16:19.884556+07	2026-06-16 14:16:37.1705+07		mqgb53r3i1fjyn17vf	A05
3145	3e21bd44	AGV01	go_to	96	completed	2026-06-16 14:16:19.91028+07	2026-06-16 14:16:37.170889+07	2026-06-16 14:16:55.278962+07	off_route	mqgb53r3i1fjyn17vf	A05
3157	87b977ba	AGV01	go_charge	\N	completed	2026-06-16 14:26:42.12963+07	2026-06-16 14:26:42.129626+07	2026-06-16 14:26:57.060007+07	off_route	mqgbjmj463wg5wo411v	Sạc Pin
3150	e5886d4a	AGV01	go_to	96	completed	2026-06-16 14:18:17.587262+07	2026-06-16 14:18:31.512148+07	2026-06-16 14:18:48.54763+07		mqgb53r3i1fjyn17vf	A05
3154	45b6ab2c	AGV01	go_to	6	completed	2026-06-16 14:20:36.49483+07	2026-06-16 14:20:36.495498+07	2026-06-16 14:21:57.028037+07	event:continue	mqgb53r3i1fjyn17vf	A05
3144	d6bbcc70	AGV02	go_charge	\N	completed	2026-06-16 14:15:37.152281+07	2026-06-16 14:21:45.130934+07	2026-06-16 14:22:29.498257+07	charge_arrived	mqgb5deppduqstpidij	A02
3153	8315477b	AGV01	go_to	96	completed	2026-06-16 14:19:05.955547+07	2026-06-16 14:21:57.029131+07	2026-06-16 14:22:47.019195+07	event:continue	mqgb53r3i1fjyn17vf	A05
3196	099c09dd	AGV02	go_to	96	cancelled	2026-06-16 16:09:18.554571+07	2026-06-16 16:09:18.556506+07	2026-06-16 16:12:57.774038+07	force-cancelled by user	mqgf1dkeaiwatba55uo	A02
3195	4a004884	AGV02	go_to	1	cancelled	2026-06-16 16:08:33.483832+07	\N	2026-06-16 16:12:57.774038+07	cancelled by user	mqgf1dkeaiwatba55uo	A02
3270	9e9fa9fe	AGV01	go_charge	\N	cancelled	2026-06-17 14:38:28.62297+07	2026-06-17 14:38:28.62297+07	2026-06-17 14:38:48.314478+07	force-cancelled by user	mqhrembvievm68kyekf	Sạc Pin
3332	ccaa6738	AGV02	go_charge	\N	completed	2026-06-17 15:37:30.405138+07	2026-06-17 15:37:30.405138+07	2026-06-17 15:37:46.561665+07		mqhtij70mgu93d4afgo	Sạc Pin
3361	639b4931	AGV01	go_charge	\N	cancelled	2026-06-17 16:05:02.871056+07	2026-06-17 16:09:24.931909+07	2026-06-17 16:15:41.262242+07	force-cancelled by user	mqhuhy6aq5oqwhj80ab	A05
3438	546c2ebe	AGV01	go_to	19	cancelled	2026-06-18 08:52:26.141202+07	\N	2026-06-18 08:53:15.191439+07	cancelled by user	mqiuhgk4zr1nj2r6ko	A02
3426	b0ebe2e1	AGV02	go_to	8	completed	2026-06-18 08:15:44.06336+07	2026-06-18 08:15:44.067367+07	2026-06-18 08:16:23.761406+07	off_route	mqit33af6cot1unb2zx	A05
3428	ff6d56a6	AGV02	go_to	15	cancelled	2026-06-18 08:16:23.760416+07	2026-06-18 08:16:23.762406+07	2026-06-18 08:40:06.863419+07	force-cancelled by user	mqit33af6cot1unb2zx	A05
3427	df7ee12f	AGV02	go_to	8	cancelled	2026-06-18 08:15:44.14187+07	\N	2026-06-18 08:40:06.864424+07	cancelled by user	mqit33af6cot1unb2zx	A05
3440	54072704	AGV01	go_charge	\N	cancelled	2026-06-18 08:52:26.154779+07	\N	2026-06-18 08:53:17.581846+07	cancelled by user	mqiuhgk4zr1nj2r6ko	A02
3448	2e39ef72	AGV02	go_to	19	completed	2026-06-18 08:54:31.603664+07	2026-06-18 08:54:50.471816+07	2026-06-18 08:55:16.030103+07	event:continue	mqiuj988eyw7f3ggq4l	A02
3443	7ddbcd4f	AGV02	go_to	19	completed	2026-06-18 08:53:49.982224+07	2026-06-18 08:54:12.190807+07	2026-06-18 08:54:31.582568+07		mqiuj988eyw7f3ggq4l	A02
3452	697ab805	AGV01	go_to	69	cancelled	2026-06-19 11:30:58.842349+07	\N	2026-06-19 11:31:26.45547+07	cancelled by user	\N	\N
3436	7ee3e386	AGV01	go_to	15	completed	2026-06-18 08:52:09.075008+07	2026-06-18 08:54:47.711281+07	2026-06-18 08:55:10.227996+07		mqiuh3by2ycpfx3pkt2	A02
3445	efc011b9	AGV02	go_to	18	completed	2026-06-18 08:53:50.028127+07	2026-06-18 08:59:44.624964+07	2026-06-18 09:01:15.083048+07	lifecycle:picking:confirmed	mqiuj988eyw7f3ggq4l	A02
3458	4874f3d7	AGV01	go_to	96	cancelled	2026-06-19 15:46:33.547302+07	\N	2026-06-19 15:48:57.84085+07	cancelled by user	\N	\N
2369	d8a6fd0d	AGV02	go_to	4	cancelled	2026-06-08 16:28:51.468485+07	\N	2026-06-08 16:29:18.752795+07	cancelled by user	mq50aqsh20kqt7ebfyt	A06
2370	a5ba1afb	AGV02	go_to	64	cancelled	2026-06-08 16:29:08.293559+07	2026-06-08 16:29:08.295562+07	2026-06-08 16:29:18.751794+07	force-cancelled by user	mq50aqsh20kqt7ebfyt	A06
2354	c7fe5d32	AGV01	go_to	17	cancelled	2026-06-08 16:26:05.428124+07	\N	2026-06-08 16:29:28.64236+07	cancelled by user	mq50acehnmt7w92qkke	A06
2372	e98237d1	AGV01	go_charge	\N	cancelled	2026-06-08 16:29:33.804985+07	2026-06-08 16:29:33.804985+07	2026-06-08 16:29:53.012658+07	force-cancelled by user	mq50et7ucm44s44g448	Sạc Pin
2813	3ffb5586	AGV01	go_charge	\N	completed	2026-06-15 11:15:10.868077+07	2026-06-15 11:20:29.358866+07	2026-06-15 11:21:37.293707+07	charge_arrived	mqep6qo99u0kysy66rp	yield_resume
2374	86f295e8	AGV01	go_charge	\N	completed	2026-06-08 16:29:58.953044+07	2026-06-08 16:30:14.629904+07	2026-06-08 16:31:17.004728+07	charge_arrived	mq50fclnd6bqq0iq15s	Sạc Pin
2888	17b9af10	AGV02	go_to	19	completed	2026-06-15 13:44:38.829806+07	2026-06-15 13:44:38.829792+07	2026-06-15 13:45:00.355634+07	lifecycle:picking:confirmed	mqeukn7y2gbw9ud6gdr	dest_retry
2891	a4d4938e	AGV01	go_to	19	completed	2026-06-15 13:48:41.211421+07	2026-06-15 13:48:41.21141+07	2026-06-15 13:49:13.786544+07	lifecycle:picking:confirmed	mqeuqvwgx5hgrclan	A06
2894	d6158221	AGV02	go_to	19	completed	2026-06-15 13:48:49.028965+07	2026-06-15 13:48:49.028956+07	2026-06-15 13:49:24.558178+07		mqeur1xr0aafme4lhyd	A06
3143	1c84539c	AGV02	go_to	18	completed	2026-06-16 14:15:37.150978+07	2026-06-16 14:20:53.3412+07	2026-06-16 14:21:07.317941+07		mqgb5deppduqstpidij	A02
3271	7368a599	AGV01	go_to	19	completed	2026-06-17 15:06:48.775983+07	2026-06-17 15:06:48.774922+07	2026-06-17 15:07:29.02894+07	lifecycle:picking:confirmed	mqhsf1zpsqjkenlbmq8	A05
2898	32a13044	AGV02	go_to	17	completed	2026-06-15 13:49:49.657936+07	2026-06-15 13:50:05.642901+07	2026-06-15 13:50:23.779586+07	lifecycle:picking:confirmed	mqeur1xr0aafme4lhyd	A06
3140	6a60484d	AGV01	go_charge	\N	cancelled	2026-06-16 14:15:24.674844+07	2026-06-16 14:25:18.012767+07	2026-06-16 14:26:35.167496+07	force-cancelled by user	mqgb53r3i1fjyn17vf	A05
2897	3b0052f4	AGV02	go_charge	\N	completed	2026-06-15 13:48:49.061372+07	2026-06-15 13:50:23.779659+07	2026-06-15 13:50:40.263153+07		mqeur1xr0aafme4lhyd	A06
2899	481eea3e	AGV02	go_charge	\N	completed	2026-06-15 13:50:23.794788+07	2026-06-15 13:50:40.263648+07	2026-06-15 13:51:55.977538+07	charge_arrived	mqeur1xr0aafme4lhyd	A06
2893	af9d248e	AGV01	go_charge	\N	completed	2026-06-15 13:48:41.226226+07	2026-06-15 13:49:59.498888+07	2026-06-15 13:51:55.980664+07	charge_arrived	mqeuqvwgx5hgrclan	A06
2900	a6848097	AGV01	go_to	19	completed	2026-06-15 13:52:51.142544+07	2026-06-15 13:52:51.142524+07	2026-06-15 13:53:27.700516+07	lifecycle:picking:confirmed	mqeuw8qifzw9xky6xr7	A06
2904	e58aae90	AGV02	go_to	19	completed	2026-06-15 13:53:02.10932+07	2026-06-15 13:53:36.743907+07	2026-06-15 13:54:07.961164+07	lifecycle:picking:confirmed	mqeuwh6oeifpgss7nvv	A06
3198	fc1a8e7c	AGV02	go_charge	\N	completed	2026-06-16 16:13:04.71062+07	2026-06-16 16:13:04.71062+07	2026-06-16 16:13:24.042467+07		mqgfcfd1bsnqpwctpe	Sạc Pin
3287	c64cd390	AGV02	go_charge	\N	cancelled	2026-06-17 15:14:06.93001+07	2026-06-17 15:14:06.93001+07	2026-06-17 15:14:23.12128+07	force-cancelled by user	mqhsog9gy5yu6anh65k	Sạc Pin
2906	261b7a4d	AGV02	go_charge	\N	completed	2026-06-15 13:53:02.136681+07	2026-06-15 13:54:58.905716+07	2026-06-15 13:55:13.514621+07		mqeuwh6oeifpgss7nvv	A06
2907	94f7705f	AGV01	go_charge	\N	completed	2026-06-15 13:53:55.879022+07	2026-06-15 13:54:15.062193+07	2026-06-15 13:55:49.280493+07	charge_arrived	mqeuw8qifzw9xky6xr7	A06
3199	900dcde4	AGV02	go_charge	\N	completed	2026-06-16 16:13:04.744969+07	2026-06-16 16:13:24.043375+07	2026-06-16 16:14:15.867407+07	charge_arrived	mqgfcfd1bsnqpwctpe	Sạc Pin
2963	4d6a1f00	AGV02	go_to	17	completed	2026-06-16 09:36:06.690203+07	2026-06-16 09:36:24.7579+07	2026-06-16 09:37:39.994025+07	lifecycle:picking:confirmed	mqg14vt8t650n3d0wp	A02
2964	d6bd34e7	AGV01	go_to	18	completed	2026-06-16 09:37:43.952348+07	2026-06-16 09:37:58.51581+07	2026-06-16 09:39:03.262977+07	event:continue	mqg14iloc21p3h8ya4	A02
3031	ef553c33	AGV01	go_to	19	completed	2026-06-16 11:10:01.802612+07	2026-06-16 11:10:37.544334+07	2026-06-16 11:10:37.556964+07	dest_wait	mqg4ip6rvwvjk57emj	A05
3032	ea0ebb34	AGV01	go_to	69	completed	2026-06-16 11:10:01.8222+07	2026-06-16 11:24:34.925732+07	2026-06-16 11:26:01.423134+07	lifecycle:picking:confirmed	mqg4ip6rvwvjk57emj	A05
3092	27b7cf0f	AGV02	go_charge	\N	completed	2026-06-16 13:12:29.631031+07	2026-06-16 13:12:29.63102+07	2026-06-16 13:12:44.001443+07		mqg8w6yzewf57vqu4r5	Sạc Pin
3147	21473083	AGV01	go_to	9	completed	2026-06-16 14:16:55.278403+07	2026-06-16 14:16:55.279172+07	2026-06-16 14:17:08.375953+07		mqgb53r3i1fjyn17vf	A05
3146	8cfe1a10	AGV01	go_to	96	completed	2026-06-16 14:16:37.213304+07	2026-06-16 14:17:32.572916+07	2026-06-16 14:18:17.554412+07		mqgb53r3i1fjyn17vf	A05
3141	71d74c98	AGV02	go_to	19	completed	2026-06-16 14:15:37.128526+07	2026-06-16 14:15:37.128517+07	2026-06-16 14:18:42.262058+07	event:continue	mqgb5deppduqstpidij	A02
3206	a6dac730	AGV02	go_to	19	completed	2026-06-16 16:15:11.905031+07	2026-06-16 16:15:11.905031+07	2026-06-16 16:15:39.07084+07		mqgff5fpn74uc400zj	A02
3278	d9391d83	AGV02	go_to	19	completed	2026-06-17 15:07:13.359758+07	2026-06-17 15:07:35.681535+07	2026-06-17 15:08:02.405539+07	lifecycle:picking:confirmed	mqhsfl2pa78j54i9pku	A05
3208	bc93d93d	AGV02	go_to	17	completed	2026-06-16 16:15:11.935522+07	2026-06-16 16:16:07.551547+07	2026-06-16 16:16:28.87403+07	lifecycle:picking:confirmed	mqgff5fpn74uc400zj	A02
3272	d9fc7422	AGV01	go_to	15	completed	2026-06-17 15:06:48.855922+07	2026-06-17 15:08:01.259229+07	2026-06-17 15:08:18.488663+07		mqhsf1zpsqjkenlbmq8	A05
3209	b450a143	AGV02	go_to	15	completed	2026-06-16 16:15:11.939735+07	2026-06-16 16:16:28.87403+07	2026-06-16 16:16:43.562113+07		mqgff5fpn74uc400zj	A02
3203	0ff22ec9	AGV01	go_to	15	completed	2026-06-16 16:14:56.171038+07	2026-06-16 16:16:31.84055+07	2026-06-16 16:16:47.314482+07	lifecycle:picking:confirmed	mqgfetauzd1yuo6yb89	A05
3205	e34122d9	AGV01	go_charge	\N	completed	2026-06-16 16:14:56.177038+07	2026-06-16 16:17:21.7788+07	2026-06-16 16:17:37.069481+07		mqgfetauzd1yuo6yb89	A05
3214	9ff2db76	AGV01	go_to	19	completed	2026-06-16 16:26:30.743222+07	2026-06-16 16:26:30.743222+07	2026-06-16 16:27:02.799229+07	event:continue	mqgftpa7owxsvi8mh7	A05
3284	cc1031ca	AGV01	go_to	15	completed	2026-06-17 15:08:01.339799+07	2026-06-17 15:08:18.490671+07	2026-06-17 15:08:55.697696+07	event:continue	mqhsf1zpsqjkenlbmq8	A05
3216	ebcf661f	AGV01	go_to	17	completed	2026-06-16 16:26:30.92399+07	2026-06-16 16:27:20.004783+07	2026-06-16 16:27:43.76441+07	event:continue	mqgftpa7owxsvi8mh7	A05
3288	46975971	AGV02	go_charge	\N	completed	2026-06-17 15:14:28.05097+07	2026-06-17 15:14:28.05097+07	2026-06-17 15:14:43.009386+07		mqhsowjvw2nb4s34tdt	Sạc Pin
3280	967b21af	AGV02	go_to	18	completed	2026-06-17 15:07:13.474528+07	2026-06-17 15:09:28.174818+07	2026-06-17 15:09:54.415815+07		mqhsfl2pa78j54i9pku	A05
3380	2b4388f4	AGV01	go_to	19	completed	2026-06-17 16:38:14.105418+07	2026-06-17 16:38:14.105418+07	2026-06-17 16:39:03.912474+07	lifecycle:picking:confirmed	mqhvomjojv5d8mg1ys	A05
3282	4fbbea60	AGV02	go_to	15	completed	2026-06-17 15:07:13.482529+07	2026-06-17 15:10:55.880525+07	2026-06-17 15:11:15.849938+07		mqhsfl2pa78j54i9pku	A05
3289	6935b190	AGV02	go_charge	\N	completed	2026-06-17 15:14:28.074258+07	2026-06-17 15:14:43.009386+07	2026-06-17 15:15:07.148925+07	off_route	mqhsowjvw2nb4s34tdt	Sạc Pin
3275	181b01f8	AGV01	go_charge	\N	cancelled	2026-06-17 15:06:48.880824+07	\N	2026-06-17 15:15:48.932+07	cancelled by user	mqhsf1zpsqjkenlbmq8	A05
3301	f167d005	AGV02	go_to	64	cancelled	2026-06-17 15:16:14.206678+07	2026-06-17 15:16:14.207662+07	2026-06-17 15:16:21.256438+07	force-cancelled by user	mqhsowjvw2nb4s34tdt	Sạc Pin
3334	798ee26b	AGV01	go_to	4	completed	2026-06-17 15:37:34.732852+07	2026-06-17 15:37:34.733867+07	2026-06-17 15:37:50.018145+07		mqhti3hmhclorilf5sd	Sạc Pin
3333	e0b334a2	AGV02	go_charge	\N	completed	2026-06-17 15:37:30.428288+07	2026-06-17 15:37:46.561665+07	2026-06-17 15:37:50.387875+07	yield_siding	mqhtij70mgu93d4afgo	Sạc Pin
3397	d8d33632	AGV02	go_to	15	completed	2026-06-17 16:41:25.214531+07	2026-06-17 16:41:25.214531+07	2026-06-17 16:41:32.784711+07	parked_siding	mqhvoyr9beumsloftrw	yield_siding
3382	c9b9e731	AGV01	go_to	15	completed	2026-06-17 16:38:14.418014+07	2026-06-17 16:39:30.886934+07	2026-06-17 16:39:46.491675+07		mqhvomjojv5d8mg1ys	A05
3390	aa59a52f	AGV02	go_to	17	completed	2026-06-17 16:38:29.883918+07	2026-06-17 16:43:49.923726+07	2026-06-17 16:44:05.014193+07	lifecycle:picking:confirmed	mqhvoyr9beumsloftrw	A05
3399	b4a8a333	AGV02	go_to	18	completed	2026-06-17 16:42:13.443767+07	2026-06-17 16:42:13.446763+07	2026-06-17 16:42:46.214157+07	off_route	mqhvoyr9beumsloftrw	yield_resume
3400	0417d3bd	AGV02	go_to	18	completed	2026-06-17 16:42:46.213148+07	2026-06-17 16:42:46.215152+07	2026-06-17 16:43:00.654836+07		mqhvoyr9beumsloftrw	yield_resume
3453	d6bb4796	AGV01	go_to	18	queued	2026-06-19 11:47:23.84834+07	\N	\N	\N	\N	\N
3383	a8ec3d89	AGV01	go_charge	\N	completed	2026-06-17 16:38:14.448563+07	2026-06-17 16:42:29.87363+07	2026-06-17 16:43:52.7859+07	charge_arrived	mqhvomjojv5d8mg1ys	A05
2355	982a7f76	AGV01	go_charge	\N	cancelled	2026-06-08 16:26:05.429127+07	\N	2026-06-08 16:29:28.64236+07	cancelled by user	mq50acehnmt7w92qkke	A06
2373	be937b75	AGV01	go_charge	\N	completed	2026-06-08 16:29:58.931262+07	2026-06-08 16:29:58.931262+07	2026-06-08 16:30:14.628919+07		mq50fclnd6bqq0iq15s	Sạc Pin
2378	31077f6e	AGV02	go_to	19	completed	2026-06-09 08:10:06.40165+07	2026-06-09 08:10:06.40165+07	2026-06-09 08:10:20.081164+07		mq5y0cvn0l4bi3gpqs7	A06
2395	720f6000	AGV01	go_charge	\N	cancelled	2026-06-09 08:39:49.648369+07	2026-06-09 08:40:07.609768+07	2026-06-09 08:41:49.912563+07	force-cancelled by user	mq5ynnfpd27q3qrh9o	A06
2375	1204238b	AGV01	go_to	19	completed	2026-06-09 08:09:54.627298+07	2026-06-09 08:09:54.627298+07	2026-06-09 08:10:29.14819+07	lifecycle:picking:confirmed	mq5y03sfy152u3qcokb	A06
2379	47c840d0	AGV02	go_to	19	completed	2026-06-09 08:10:06.410167+07	2026-06-09 08:10:20.081164+07	2026-06-09 08:10:40.36029+07		mq5y0cvn0l4bi3gpqs7	A06
2382	65c6548f	AGV02	go_to	19	completed	2026-06-09 08:10:20.213784+07	2026-06-09 08:10:40.36029+07	2026-06-09 08:11:06.808674+07	lifecycle:picking:confirmed	mq5y0cvn0l4bi3gpqs7	A06
2376	30c7273d	AGV01	go_to	17	completed	2026-06-09 08:09:54.809389+07	2026-06-09 08:10:29.14819+07	2026-06-09 08:11:36.328526+07	lifecycle:picking:confirmed	mq5y03sfy152u3qcokb	A06
2377	391d6308	AGV01	go_charge	\N	completed	2026-06-09 08:09:54.812392+07	2026-06-09 08:11:36.329525+07	2026-06-09 08:11:52.340368+07		mq5y03sfy152u3qcokb	A06
2380	044db9aa	AGV02	go_to	17	cancelled	2026-06-09 08:10:06.423685+07	2026-06-09 08:11:06.808674+07	2026-06-09 08:23:20.031583+07	force-cancelled by user	mq5y0cvn0l4bi3gpqs7	A06
2383	ef21d393	AGV02	go_to	17	cancelled	2026-06-09 08:11:06.822093+07	\N	2026-06-09 08:23:20.031583+07	cancelled by user	mq5y0cvn0l4bi3gpqs7	A06
2381	29e9adbc	AGV02	go_charge	\N	cancelled	2026-06-09 08:10:06.424689+07	\N	2026-06-09 08:23:20.031583+07	cancelled by user	mq5y0cvn0l4bi3gpqs7	A06
2384	ae22e327	AGV01	go_charge	\N	completed	2026-06-09 08:11:36.377538+07	2026-06-09 08:11:52.341366+07	2026-06-09 08:24:32.97775+07	charge_arrived	mq5y03sfy152u3qcokb	A06
2385	6bf5b19a	AGV01	go_to	19	completed	2026-06-09 08:28:13.215305+07	2026-06-09 08:28:13.215305+07	2026-06-09 08:28:47.125493+07	lifecycle:picking:confirmed	mq5ynnfpd27q3qrh9o	A06
2388	2483d904	AGV02	go_to	19	completed	2026-06-09 08:28:24.107084+07	2026-06-09 08:28:24.107084+07	2026-06-09 08:28:58.360663+07		mq5ynvvmf4uk81fbqqn	A06
2389	3e9bac1c	AGV02	go_to	19	completed	2026-06-09 08:28:24.113537+07	2026-06-09 08:28:58.366626+07	2026-06-09 08:29:20.968727+07	lifecycle:picking:confirmed	mq5ynvvmf4uk81fbqqn	A06
2398	342ba950	AGV01	go_to	19	completed	2026-06-09 09:00:36.21212+07	2026-06-09 09:00:36.21212+07	2026-06-09 09:01:15.275589+07	lifecycle:picking:confirmed	mq5ztaoa11anr5qb2yy	A06
2408	db96296b	AGV02	go_charge	\N	completed	2026-06-09 09:21:58.850869+07	2026-06-09 09:22:15.895409+07	2026-06-09 09:22:48.797818+07	charge_arrived	mq60ksdqe0o2hoc1nia	Sạc Pin
2390	e3ff9dd3	AGV02	go_to	17	completed	2026-06-09 08:28:24.128548+07	2026-06-09 08:29:20.968727+07	2026-06-09 08:29:38.010043+07		mq5ynvvmf4uk81fbqqn	A06
2392	b96bb667	AGV02	go_to	17	completed	2026-06-09 08:29:20.977727+07	2026-06-09 08:29:38.011037+07	2026-06-09 08:29:56.84543+07		mq5ynvvmf4uk81fbqqn	A06
2410	0b1d321f	AGV01	go_charge	\N	completed	2026-06-09 09:22:39.811323+07	2026-06-09 09:22:39.811323+07	2026-06-09 09:22:55.632254+07		mq60lo0el9yiloj2k3r	Sạc Pin
2393	7d9351d4	AGV02	go_to	17	completed	2026-06-09 08:29:38.03104+07	2026-06-09 08:29:56.846427+07	2026-06-09 08:29:56.858949+07	dest_wait	mq5ynvvmf4uk81fbqqn	A06
2401	55d90298	AGV02	go_to	19	completed	2026-06-09 09:00:47.872611+07	2026-06-09 09:00:47.87161+07	2026-06-09 09:01:21.42448+07		mq5ztjosb75y6i6cp75	A06
2391	9b5989d0	AGV02	go_charge	\N	completed	2026-06-09 08:28:24.129546+07	2026-06-09 08:29:56.858949+07	2026-06-09 08:30:15.51061+07		mq5ynvvmf4uk81fbqqn	A06
2402	541684e8	AGV02	go_to	19	completed	2026-06-09 09:00:47.877609+07	2026-06-09 09:01:21.42448+07	2026-06-09 09:01:57.011544+07	lifecycle:picking:confirmed	mq5ztjosb75y6i6cp75	A06
2394	7b30cbdb	AGV02	go_charge	\N	completed	2026-06-09 08:29:56.873958+07	2026-06-09 08:30:15.511563+07	2026-06-09 08:30:53.151176+07	charge_arrived	mq5ynvvmf4uk81fbqqn	A06
2387	4cac7e6a	AGV01	go_to	17	completed	2026-06-09 08:28:13.331522+07	2026-06-09 08:28:47.126488+07	2026-06-09 08:39:49.401259+07	lifecycle:picking:confirmed	mq5ynnfpd27q3qrh9o	A06
2419	64be54b9	AGV02	go_to	19	completed	2026-06-09 09:43:48.245382+07	2026-06-09 09:44:10.462597+07	2026-06-09 09:44:10.471607+07	dest_wait	mq61cksdaufe7024d7h	A06
2386	3f4bdf06	AGV01	go_charge	\N	completed	2026-06-09 08:28:13.332476+07	2026-06-09 08:39:49.402256+07	2026-06-09 08:40:07.602924+07		mq5ynnfpd27q3qrh9o	A06
2411	b7433831	AGV01	go_charge	\N	completed	2026-06-09 09:22:39.835859+07	2026-06-09 09:22:55.639263+07	2026-06-09 09:23:48.067879+07	charge_arrived	mq60lo0el9yiloj2k3r	Sạc Pin
2396	6c848274	AGV02	go_to	17	cancelled	2026-06-09 08:40:07.619784+07	2026-06-09 08:40:07.619784+07	2026-06-09 08:40:49.471901+07	force-cancelled by user	\N	dest_retry
2397	d09542fd	AGV02	go_to	17	cancelled	2026-06-09 08:40:07.746128+07	\N	2026-06-09 08:40:49.471901+07	cancelled by user	\N	dest_retry
2400	96c89e2e	AGV01	go_to	17	completed	2026-06-09 09:00:36.263154+07	2026-06-09 09:01:15.276578+07	2026-06-09 09:01:59.130156+07	lifecycle:picking:confirmed	mq5ztaoa11anr5qb2yy	A06
2403	f6962e3a	AGV02	go_to	17	completed	2026-06-09 09:00:47.893989+07	2026-06-09 09:01:57.011544+07	2026-06-09 09:02:13.962253+07		mq5ztjosb75y6i6cp75	A06
2399	59830cdc	AGV01	go_charge	\N	completed	2026-06-09 09:00:36.266124+07	2026-06-09 09:01:59.131154+07	2026-06-09 09:02:14.983295+07		mq5ztaoa11anr5qb2yy	A06
2406	94bbaac8	AGV01	go_charge	\N	cancelled	2026-06-09 09:01:59.148677+07	2026-06-09 09:02:14.984299+07	2026-06-09 09:21:42.117864+07	force-cancelled by user	mq5ztaoa11anr5qb2yy	A06
2405	45c8d1f5	AGV02	go_to	17	cancelled	2026-06-09 09:01:57.022542+07	2026-06-09 09:02:13.967307+07	2026-06-09 09:21:48.584477+07	force-cancelled by user	mq5ztjosb75y6i6cp75	A06
2404	2fe077b8	AGV02	go_charge	\N	cancelled	2026-06-09 09:00:47.894991+07	\N	2026-06-09 09:21:48.59848+07	cancelled by user	mq5ztjosb75y6i6cp75	A06
2407	527462be	AGV02	go_charge	\N	completed	2026-06-09 09:21:58.828566+07	2026-06-09 09:21:58.828566+07	2026-06-09 09:22:15.893427+07		mq60ksdqe0o2hoc1nia	Sạc Pin
2412	d9ce54f6	AGV01	go_to	19	completed	2026-06-09 09:43:17.092713+07	2026-06-09 09:43:17.092713+07	2026-06-09 09:44:19.54428+07	lifecycle:picking:confirmed	mq61c6nfez1zigsnhlr	A06
2409	947065a9	AGV01	go_charge	\N	cancelled	2026-06-09 09:22:12.441799+07	2026-06-09 09:22:12.441799+07	2026-06-09 09:22:34.646802+07	force-cancelled by user	mq60l2wdma5jnzagh9	Sạc Pin
2420	6985866a	AGV02	go_to	19	completed	2026-06-09 09:44:26.841422+07	2026-06-09 09:44:26.841422+07	2026-06-09 09:44:58.96342+07	lifecycle:picking:confirmed	\N	dest_retry
2415	19cbfb27	AGV02	go_to	19	completed	2026-06-09 09:43:35.377646+07	2026-06-09 09:43:35.377646+07	2026-06-09 09:43:48.096301+07		mq61cksdaufe7024d7h	A06
2416	2f3045b2	AGV02	go_to	19	completed	2026-06-09 09:43:35.38661+07	2026-06-09 09:43:48.096301+07	2026-06-09 09:44:10.461601+07		mq61cksdaufe7024d7h	A06
2418	76300f3b	AGV02	go_charge	\N	cancelled	2026-06-09 09:43:35.404611+07	\N	2026-06-09 10:03:41.591934+07	cancelled by user	mq61cksdaufe7024d7h	A06
2414	8da4233b	AGV01	go_to	17	completed	2026-06-09 09:43:17.299756+07	2026-06-09 09:44:19.552283+07	2026-06-09 09:44:54.236799+07	lifecycle:picking:confirmed	mq61c6nfez1zigsnhlr	A06
2421	79ba43b4	AGV02	go_to	19	completed	2026-06-09 09:44:26.873934+07	2026-06-09 09:44:58.96442+07	2026-06-09 09:45:13.175766+07	lifecycle:picking:confirmed	\N	dest_retry
2413	b4f37b61	AGV01	go_charge	\N	completed	2026-06-09 09:43:17.301763+07	2026-06-09 09:44:54.236799+07	2026-06-09 09:45:10.20722+07		mq61c6nfez1zigsnhlr	A06
2425	d9fb6e87	AGV01	go_to	19	completed	2026-06-09 10:30:24.523294+07	2026-06-09 10:30:24.523294+07	2026-06-09 10:34:06.900526+07	lifecycle:picking:confirmed	mq630sbdz8kiunfoznm	A06
2422	d6fc246c	AGV01	go_charge	\N	cancelled	2026-06-09 09:44:54.313366+07	2026-06-09 09:45:10.209222+07	2026-06-09 10:03:47.276489+07	force-cancelled by user	mq61c6nfez1zigsnhlr	A06
2417	644252e0	AGV02	go_to	17	cancelled	2026-06-09 09:43:35.401668+07	2026-06-09 09:45:13.175766+07	2026-06-09 10:03:41.59094+07	force-cancelled by user	mq61cksdaufe7024d7h	A06
2423	4667d9e0	AGV02	go_charge	\N	cancelled	2026-06-09 10:04:03.685258+07	2026-06-09 10:04:03.685258+07	2026-06-09 10:04:55.743864+07	force-cancelled by user	mq622wjsnhhjmkpuvn9	Sạc Pin
2424	c9bf7368	AGV02	go_charge	\N	cancelled	2026-06-09 10:04:03.708154+07	\N	2026-06-09 10:04:55.743864+07	cancelled by user	mq622wjsnhhjmkpuvn9	Sạc Pin
2426	9ff9fa5e	AGV01	go_to	17	completed	2026-06-09 10:30:24.688872+07	2026-06-09 10:34:06.900526+07	2026-06-09 10:34:56.666705+07	lifecycle:picking:confirmed	mq630sbdz8kiunfoznm	A06
2427	70eb064f	AGV01	go_charge	\N	running	2026-06-09 10:30:24.69387+07	2026-06-09 10:34:56.667713+07	\N		mq630sbdz8kiunfoznm	A06
2822	738baa88	AGV02	go_to	17	completed	2026-06-15 11:37:46.710435+07	2026-06-15 11:38:58.046729+07	2026-06-15 11:39:36.782042+07	lifecycle:picking:confirmed	mqeq2j9oggp54vve77m	A06
2431	7e3d9dbf	AGV02	go_charge	\N	queued	2026-06-09 10:30:37.975223+07	\N	\N	\N	mq6312kyftobuawz2df	A06
2428	e8e5a30c	AGV02	go_to	19	completed	2026-06-09 10:30:37.780155+07	2026-06-09 10:30:37.780155+07	2026-06-09 10:30:51.600442+07		mq6312kyftobuawz2df	A06
2434	6186adf6	AGV02	go_to	17	completed	2026-06-09 10:34:32.497919+07	2026-06-09 10:34:49.476546+07	2026-06-09 10:35:07.670266+07		mq6312kyftobuawz2df	A06
2817	b66e7d39	AGV01	go_to	19	completed	2026-06-15 11:37:40.166623+07	2026-06-15 11:37:40.166602+07	2026-06-15 11:38:13.999469+07	lifecycle:picking:confirmed	mqeq2e99a7k13fe8jm6	A06
3338	b7ed13d9	AGV02	go_charge	\N	cancelled	2026-06-17 15:38:25.385224+07	\N	2026-06-17 15:38:42.734086+07	cancelled by user	mqhtjploj4o2x35abyr	Sạc Pin
2820	3f811377	AGV02	go_to	19	completed	2026-06-15 11:37:46.664276+07	2026-06-15 11:37:46.664254+07	2026-06-15 11:38:21.380037+07		mqeq2j9oggp54vve77m	A06
3099	349ae7d7	AGV01	go_charge	\N	completed	2026-06-16 13:25:48.16739+07	2026-06-16 14:02:39.035217+07	2026-06-16 14:02:54.335293+07		mqg9db1mma8mrrvp1aa	A05
2818	193795b2	AGV01	go_to	17	completed	2026-06-15 11:37:40.214876+07	2026-06-15 11:38:13.999605+07	2026-06-15 11:38:52.900713+07	lifecycle:picking:confirmed	mqeq2e99a7k13fe8jm6	A06
2821	7e2e9037	AGV02	go_to	19	completed	2026-06-15 11:37:46.671641+07	2026-06-15 11:38:21.38037+07	2026-06-15 11:38:58.046474+07	lifecycle:picking:confirmed	mqeq2j9oggp54vve77m	A06
2819	eda5163b	AGV01	go_charge	\N	completed	2026-06-15 11:37:40.216149+07	2026-06-15 11:38:52.900818+07	2026-06-15 11:39:00.358017+07	off_route	mqeq2e99a7k13fe8jm6	A06
3160	665869b8	AGV01	go_to	2	cancelled	2026-06-16 14:26:57.213141+07	\N	2026-06-16 14:26:57.845198+07	cancelled by user	mqgbjmj463wg5wo411v	Sạc Pin
2823	11e96126	AGV02	go_charge	\N	completed	2026-06-15 11:37:46.712819+07	2026-06-15 11:39:36.782218+07	2026-06-15 11:40:37.662099+07		mqeq2j9oggp54vve77m	A06
2824	374b6ddc	AGV01	go_charge	\N	completed	2026-06-15 11:38:52.916542+07	2026-06-15 11:40:12.814427+07	2026-06-15 11:41:22.037452+07	charge_arrived	mqeq2e99a7k13fe8jm6	A06
2909	e53d5196	AGV01	go_to	19	completed	2026-06-16 09:01:08.683971+07	2026-06-16 09:01:08.683961+07	2026-06-16 09:01:52.219369+07	lifecycle:picking:confirmed	mqfzwyf1os41n68iyo	A06
2910	7b5378df	AGV01	go_to	17	completed	2026-06-16 09:01:08.720837+07	2026-06-16 09:01:52.219667+07	2026-06-16 09:02:16.513647+07	lifecycle:picking:confirmed	mqfzwyf1os41n68iyo	A06
2914	4df9614b	AGV02	go_to	17	completed	2026-06-16 09:01:18.276432+07	2026-06-16 09:02:20.562937+07	2026-06-16 09:03:49.879876+07	event:continue	mqfzx5tha60osk3utge	A06
2965	109e17c7	AGV01	go_to	19	completed	2026-06-16 09:50:00.760434+07	2026-06-16 09:50:00.760425+07	2026-06-16 09:50:33.424935+07	lifecycle:picking:confirmed	mqg1nst13z14xqfi246	A02
3202	9d082ea6	AGV01	go_to	17	completed	2026-06-16 16:14:56.166036+07	2026-06-16 16:15:33.591941+07	2026-06-16 16:15:56.8258+07	lifecycle:picking:confirmed	mqgfetauzd1yuo6yb89	A05
2974	1ca3e8ef	AGV02	go_to	19	completed	2026-06-16 09:50:24.784779+07	2026-06-16 09:50:46.01724+07	2026-06-16 09:51:05.903295+07	lifecycle:picking:confirmed	mqg1o1wl6h93q5wbixm	A02
2966	2bb8aa26	AGV01	go_to	15	completed	2026-06-16 09:50:00.928343+07	2026-06-16 09:50:54.295789+07	2026-06-16 09:51:09.489641+07		mqg1nst13z14xqfi246	A02
3339	0cef639c	AGV02	go_charge	\N	cancelled	2026-06-17 15:39:09.64053+07	2026-06-17 15:39:09.64053+07	2026-06-17 15:39:19.601807+07	force-cancelled by user	mqhtij70mgu93d4afgo	yield_resume
3041	5bfb1a0f	AGV01	go_to	96	completed	2026-06-16 11:12:42.974122+07	2026-06-16 11:13:02.166938+07	2026-06-16 11:13:21.017592+07	off_route	mqg4ip6rvwvjk57emj	A05
3211	6880f58a	AGV02	go_to	15	completed	2026-06-16 16:16:28.895582+07	2026-06-16 16:16:43.564119+07	2026-06-16 16:16:43.581656+07	dest_wait	mqgff5fpn74uc400zj	A02
3037	997f36b7	AGV02	go_to	18	completed	2026-06-16 11:10:16.397403+07	2026-06-16 11:13:45.388811+07	2026-06-16 11:14:05.426321+07	lifecycle:picking:confirmed	mqg4j0j3qqi1ob33vfc	A02
3039	071b1f5d	AGV02	go_charge	\N	completed	2026-06-16 11:10:16.408166+07	2026-06-16 11:15:52.826039+07	2026-06-16 11:16:07.054108+07		mqg4j0j3qqi1ob33vfc	A02
3034	c8cfed50	AGV01	go_to	15	completed	2026-06-16 11:10:01.813451+07	2026-06-16 11:23:47.450399+07	2026-06-16 11:24:02.678598+07		mqg4ip6rvwvjk57emj	A05
3102	80660212	AGV01	go_to	16	cancelled	2026-06-16 13:26:07.224922+07	\N	2026-06-16 13:26:18.523851+07	cancelled by user	mqg9dpsqq4qrrx9oib	A02
3094	ab60f9b2	AGV01	go_to	64	completed	2026-06-16 13:25:48.1053+07	2026-06-16 13:25:48.105287+07	2026-06-16 13:26:51.560316+07	lifecycle:picking:confirmed	mqg9db1mma8mrrvp1aa	A05
3108	751cc894	AGV02	go_charge	\N	cancelled	2026-06-16 13:26:47.53682+07	\N	2026-06-16 13:58:33.249856+07	cancelled by user	mqg9ekwqmgwzmof7bed	A02
3095	daaf03c3	AGV01	go_to	96	completed	2026-06-16 13:25:48.151157+07	2026-06-16 13:59:10.788354+07	2026-06-16 13:59:22.535814+07		mqg9db1mma8mrrvp1aa	A05
3097	595a7782	AGV01	go_to	15	completed	2026-06-16 13:25:48.159908+07	2026-06-16 14:00:44.332662+07	2026-06-16 14:02:02.311473+07	lifecycle:picking:confirmed	mqg9db1mma8mrrvp1aa	A05
3273	9e1149e2	AGV01	go_to	17	completed	2026-06-17 15:06:48.853869+07	2026-06-17 15:07:29.029952+07	2026-06-17 15:08:01.257232+07	event:continue	mqhsf1zpsqjkenlbmq8	A05
3439	c00f5c43	AGV01	go_to	16	cancelled	2026-06-18 08:52:26.142694+07	\N	2026-06-18 08:53:15.998204+07	cancelled by user	mqiuhgk4zr1nj2r6ko	A02
3285	36436474	AGV02	go_to	18	completed	2026-06-17 15:09:28.281842+07	2026-06-17 15:09:54.416813+07	2026-06-17 15:10:33.763491+07	event:continue	mqhsfl2pa78j54i9pku	A05
3381	41480b91	AGV01	go_to	17	completed	2026-06-17 16:38:14.412931+07	2026-06-17 16:39:03.913499+07	2026-06-17 16:39:30.886934+07	lifecycle:picking:confirmed	mqhvomjojv5d8mg1ys	A05
3281	22b87e38	AGV02	go_to	17	completed	2026-06-17 15:07:13.479523+07	2026-06-17 15:10:33.765518+07	2026-06-17 15:10:55.87832+07	event:continue	mqhsfl2pa78j54i9pku	A05
3283	e320f7b6	AGV02	go_charge	\N	cancelled	2026-06-17 15:07:13.488528+07	\N	2026-06-17 15:14:01.078921+07	cancelled by user	mqhsfl2pa78j54i9pku	A05
3274	c89db7a7	AGV01	go_to	18	cancelled	2026-06-17 15:06:48.876472+07	\N	2026-06-17 15:15:48.932+07	cancelled by user	mqhsf1zpsqjkenlbmq8	A05
3296	e0b196da	AGV02	go_to	4	cancelled	2026-06-17 15:15:40.915516+07	\N	2026-06-17 15:16:21.256438+07	cancelled by user	mqhsowjvw2nb4s34tdt	Sạc Pin
3336	bcc0551d	AGV02	go_to	9	completed	2026-06-17 15:37:50.390098+07	2026-06-17 15:37:50.390098+07	2026-06-17 15:38:04.938186+07	parked_siding	mqhtij70mgu93d4afgo	yield_siding
3337	0786fcb6	AGV02	go_charge	\N	cancelled	2026-06-17 15:38:25.36924+07	2026-06-17 15:38:25.36924+07	2026-06-17 15:38:42.734086+07	force-cancelled by user	mqhtjploj4o2x35abyr	Sạc Pin
3407	27fc0ce5	AGV02	go_to	1	cancelled	2026-06-17 16:46:10.404834+07	2026-06-17 16:46:10.405819+07	2026-06-17 16:54:29.943938+07	force-cancelled by user	mqhvoyr9beumsloftrw	A05
3406	71275ef3	AGV02	go_to	2	cancelled	2026-06-17 16:46:01.574452+07	\N	2026-06-17 16:54:29.943938+07	cancelled by user	mqhvoyr9beumsloftrw	A05
3425	b314dc6c	AGV02	go_to	16	cancelled	2026-06-18 08:15:28.47238+07	\N	2026-06-18 08:40:06.864424+07	cancelled by user	mqit33af6cot1unb2zx	A05
3431	a103cda1	AGV01	go_charge	\N	cancelled	2026-06-18 08:40:28.349746+07	\N	2026-06-18 08:40:34.179866+07	cancelled by user	mqiu1wsd2rfx45z8osp	Sạc Pin
3444	98d727cf	AGV02	go_to	16	completed	2026-06-18 08:53:50.025604+07	2026-06-18 08:55:16.033084+07	2026-06-18 08:59:44.624964+07	lifecycle:picking:confirmed	mqiuj988eyw7f3ggq4l	A02
3477	d991f887	AGV01	go_charge	\N	completed	2026-06-22 11:39:26.904385+07	2026-06-22 11:39:26.904385+07	2026-06-22 11:39:41.032408+07		mqoq7n6javlrnc32a6o	Sạc Pin
3437	d9ddfc5c	AGV01	go_charge	\N	completed	2026-06-18 08:52:09.076009+07	2026-06-18 08:59:47.819193+07	2026-06-18 09:01:27.072114+07	charge_arrived	mqiuh3by2ycpfx3pkt2	A02
3454	4e7037e9	AGV01	go_to	18	queued	2026-06-19 11:56:51.350174+07	\N	\N	\N	\N	\N
3460	9f34c4ce	AGV01	go_to	18	cancelled	2026-06-19 15:51:21.472808+07	\N	2026-06-19 15:55:27.36079+07	cancelled by user	\N	\N
3470	4bf2051c	AGV01	go_to	16	completed	2026-06-22 11:18:10.677076+07	2026-06-22 11:18:42.338264+07	2026-06-22 11:20:25.71354+07	lifecycle:picking:confirmed	\N	\N
3472	1c924c8f	AGV01	go_to	18	completed	2026-06-22 11:20:39.9201+07	2026-06-22 11:22:39.984875+07	2026-06-22 11:24:28.0246+07	lifecycle:picking:confirmed	\N	\N
3474	4b335649	AGV01	go_charge	\N	completed	2026-06-22 11:30:31.540379+07	2026-06-22 11:30:45.842179+07	2026-06-22 11:31:23.420198+07	charge_arrived	mqopw60bn1t0czb6i3k	Sạc Pin
3481	56134f65	AGV01	go_to	8	cancelled	2026-06-22 11:40:41.965013+07	2026-06-22 11:40:41.965013+07	2026-06-22 11:42:10.590156+07	force-cancelled by user	mqoq7n6javlrnc32a6o	Sạc Pin
3482	d0ba7b91	AGV01	go_to	8	cancelled	2026-06-22 11:40:41.975373+07	\N	2026-06-22 11:42:10.590156+07	cancelled by user	mqoq7n6javlrnc32a6o	Sạc Pin
3480	0a3c0161	AGV01	go_charge	\N	cancelled	2026-06-22 11:40:27.328636+07	\N	2026-06-22 11:42:10.590156+07	cancelled by user	mqoq7n6javlrnc32a6o	Sạc Pin
3488	891fc8be	AGV01	go_charge	\N	failed	2026-06-23 13:50:55.888357+07	2026-06-23 13:50:55.888357+07	2026-06-23 13:51:10.903691+07	Không tìm thấy node charge trong map 1779790224391 | candidates=['CHARGE', 'Charge', 'ChargeStation', 'Trạm sạc', 'Sac', 'Sạc']	\N	\N
2458	cf7da801	AGV01	go_charge	\N	completed	2026-06-09 14:12:09.373294+07	2026-06-09 14:14:27.956828+07	2026-06-09 14:17:40.203106+07	charge_arrived	mq6axy5et9tzugk9m1	A06
2455	78104262	AGV01	go_charge	\N	completed	2026-06-09 14:07:49.53367+07	2026-06-09 14:08:04.611811+07	2026-06-09 14:08:59.084426+07	charge_arrived	mq6asdy9af01jesgxh	Sạc Pin
2429	023ed0c9	AGV02	go_to	19	completed	2026-06-09 10:30:37.839703+07	2026-06-09 10:30:51.600949+07	2026-06-09 10:31:12.099491+07		mq6312kyftobuawz2df	A06
2432	d0545bc7	AGV02	go_to	19	completed	2026-06-09 10:30:51.871444+07	2026-06-09 10:31:12.100499+07	2026-06-09 10:31:12.110479+07	dest_wait	mq6312kyftobuawz2df	A06
2433	4bcd2d01	AGV02	go_to	19	completed	2026-06-09 10:34:15.187932+07	2026-06-09 10:34:15.187932+07	2026-06-09 10:34:32.481455+07	lifecycle:picking:confirmed	mq6312kyftobuawz2df	dest_retry
2430	aa582221	AGV02	go_to	17	completed	2026-06-09 10:30:37.97424+07	2026-06-09 10:34:32.481455+07	2026-06-09 10:34:49.475554+07		mq6312kyftobuawz2df	A06
2436	1f1a78d8	AGV01	go_charge	\N	queued	2026-06-09 10:34:56.686318+07	\N	\N	\N	mq630sbdz8kiunfoznm	A06
2435	abe356dc	AGV02	go_to	17	running	2026-06-09 10:34:49.491596+07	2026-06-09 10:35:07.670266+07	\N		mq6312kyftobuawz2df	A06
2437	e3526470	AGV02	go_charge	\N	completed	2026-06-09 11:04:48.753846+07	2026-06-09 11:04:48.753846+07	2026-06-09 11:05:04.06584+07		mq64914j9hpjjt1d6h	Sạc Pin
2439	aa73d640	AGV01	go_charge	\N	cancelled	2026-06-09 11:04:59.579496+07	2026-06-09 11:04:59.579496+07	2026-06-09 11:05:41.596852+07	force-cancelled by user	mq6499h68cvk3s5a17i	Sạc Pin
2438	c949d02f	AGV02	go_charge	\N	completed	2026-06-09 11:04:49.005689+07	2026-06-09 11:05:04.066837+07	2026-06-09 11:05:49.541869+07	charge_arrived	mq64914j9hpjjt1d6h	Sạc Pin
2443	bcc63da3	AGV02	go_to	19	completed	2026-06-09 11:10:14.307369+07	2026-06-09 11:10:14.307369+07	2026-06-09 11:10:27.000872+07		mq64g0azb0ufh1q60c6	A06
2440	ae5acf5e	AGV01	go_to	19	completed	2026-06-09 11:09:59.429186+07	2026-06-09 11:09:59.429186+07	2026-06-09 11:10:36.518739+07	lifecycle:picking:confirmed	mq64foubno1owo3zuf	A06
2444	d7b9f642	AGV02	go_to	19	completed	2026-06-09 11:10:14.31336+07	2026-06-09 11:10:27.00188+07	2026-06-09 11:10:47.360333+07		mq64g0azb0ufh1q60c6	A06
2447	507a78fd	AGV02	go_to	19	completed	2026-06-09 11:10:27.142406+07	2026-06-09 11:10:47.360333+07	2026-06-09 11:11:06.142166+07	lifecycle:picking:confirmed	mq64g0azb0ufh1q60c6	A06
2445	6018ba3e	AGV02	go_to	17	completed	2026-06-09 11:10:14.336363+07	2026-06-09 11:11:06.142166+07	2026-06-09 11:11:23.16798+07		mq64g0azb0ufh1q60c6	A06
2448	a9d0f04a	AGV02	go_to	17	completed	2026-06-09 11:11:06.157692+07	2026-06-09 11:11:23.16798+07	2026-06-09 11:11:42.054915+07		mq64g0azb0ufh1q60c6	A06
2459	8987c2d1	AGV02	go_to	19	completed	2026-06-09 14:12:24.609357+07	2026-06-09 14:12:24.609357+07	2026-06-09 14:12:37.489939+07		mq6aya6s9gvddzmxei	A06
2449	ffd817a9	AGV02	go_to	17	completed	2026-06-09 11:11:23.179964+07	2026-06-09 11:11:42.055921+07	2026-06-09 11:11:42.065918+07	dest_wait	mq64g0azb0ufh1q60c6	A06
2441	4889f2d4	AGV01	go_to	17	completed	2026-06-09 11:09:59.458725+07	2026-06-09 11:10:36.522911+07	2026-06-09 11:11:42.587778+07	lifecycle:picking:confirmed	mq64foubno1owo3zuf	A06
2467	f698feb5	AGV02	go_charge	\N	completed	2026-06-09 14:16:44.072949+07	2026-06-09 14:16:59.329737+07	2026-06-09 14:17:51.259196+07	charge_arrived	mq6aya6s9gvddzmxei	A06
2442	2c7d1a2b	AGV01	go_charge	\N	cancelled	2026-06-09 11:09:59.460736+07	2026-06-09 11:11:42.587778+07	2026-06-09 14:06:31.115422+07	force-cancelled by user	mq64foubno1owo3zuf	A06
2450	ab92b364	AGV01	go_charge	\N	cancelled	2026-06-09 11:11:42.662559+07	\N	2026-06-09 14:06:31.152811+07	cancelled by user	mq64foubno1owo3zuf	A06
2446	4ef0bfb1	AGV02	go_charge	\N	cancelled	2026-06-09 11:10:14.337359+07	\N	2026-06-09 14:06:37.336622+07	cancelled by user	mq64g0azb0ufh1q60c6	A06
2451	f38ad6b3	AGV02	go_charge	\N	completed	2026-06-09 14:06:47.67281+07	2026-06-09 14:06:47.67281+07	2026-06-09 14:06:56.803288+07		mq6ar277jyskpn8vk5	Sạc Pin
2452	23f33e04	AGV02	go_charge	\N	completed	2026-06-09 14:06:47.71071+07	2026-06-09 14:06:56.804283+07	2026-06-09 14:07:34.811093+07	charge_arrived	mq6ar277jyskpn8vk5	Sạc Pin
2453	8ca0a253	AGV01	go_charge	\N	cancelled	2026-06-09 14:07:30.081063+07	2026-06-09 14:07:30.081063+07	2026-06-09 14:07:42.712565+07	force-cancelled by user	mq6aryy9ruzo05o4agj	Sạc Pin
2454	8d47601d	AGV01	go_charge	\N	completed	2026-06-09 14:07:49.520653+07	2026-06-09 14:07:49.520653+07	2026-06-09 14:08:04.610821+07		mq6asdy9af01jesgxh	Sạc Pin
2456	3ae8019a	AGV01	go_to	19	completed	2026-06-09 14:12:09.010542+07	2026-06-09 14:12:09.010542+07	2026-06-09 14:12:42.677002+07	lifecycle:picking:confirmed	mq6axy5et9tzugk9m1	A06
2460	7fbd8ba8	AGV02	go_to	19	completed	2026-06-09 14:12:24.622357+07	2026-06-09 14:12:37.490945+07	2026-06-09 14:12:57.945177+07		mq6aya6s9gvddzmxei	A06
2463	f72a9a34	AGV02	go_to	19	completed	2026-06-09 14:12:37.627604+07	2026-06-09 14:12:57.945177+07	2026-06-09 14:13:25.465045+07	lifecycle:picking:confirmed	mq6aya6s9gvddzmxei	A06
2461	4abb9a7f	AGV02	go_to	17	completed	2026-06-09 14:12:24.655917+07	2026-06-09 14:13:25.470046+07	2026-06-09 14:13:42.725427+07		mq6aya6s9gvddzmxei	A06
2464	a3c56d97	AGV02	go_to	17	completed	2026-06-09 14:13:25.574567+07	2026-06-09 14:13:42.726451+07	2026-06-09 14:13:57.806856+07		mq6aya6s9gvddzmxei	A06
2465	2e0d1fb8	AGV02	go_to	17	completed	2026-06-09 14:13:42.959679+07	2026-06-09 14:13:57.807864+07	2026-06-09 14:13:57.817844+07	dest_wait	mq6aya6s9gvddzmxei	A06
2469	e2efb492	AGV01	go_charge	\N	completed	2026-06-09 14:24:05.021901+07	2026-06-09 14:25:25.365025+07	2026-06-09 14:25:41.383644+07		mq6bdajbqs1nemhlqw	A06
2457	3b902335	AGV01	go_to	17	completed	2026-06-09 14:12:09.370055+07	2026-06-09 14:12:42.677002+07	2026-06-09 14:14:27.956828+07	lifecycle:picking:confirmed	mq6axy5et9tzugk9m1	A06
2466	bd3eb823	AGV02	go_to	17	completed	2026-06-09 14:14:37.918373+07	2026-06-09 14:14:37.918373+07	2026-06-09 14:16:44.053965+07	lifecycle:picking:confirmed	mq6aya6s9gvddzmxei	dest_retry
2462	723397df	AGV02	go_charge	\N	completed	2026-06-09 14:12:24.657917+07	2026-06-09 14:16:44.053965+07	2026-06-09 14:16:59.328738+07		mq6aya6s9gvddzmxei	A06
2471	d46777ff	AGV01	go_to	19	completed	2026-06-09 14:24:16.820183+07	2026-06-09 14:27:34.815618+07	2026-06-09 14:28:29.955312+07	lifecycle:picking:confirmed	mq6bdjpabm40wa7t3of	A06
2468	c24e8eab	AGV01	go_to	19	completed	2026-06-09 14:24:04.85829+07	2026-06-09 14:24:04.85829+07	2026-06-09 14:24:51.73794+07	lifecycle:picking:confirmed	mq6bdajbqs1nemhlqw	A06
2475	549ba4d7	AGV02	go_to	19	cancelled	2026-06-09 14:24:45.418295+07	2026-06-09 14:25:09.297718+07	2026-06-09 14:25:57.430267+07	force-cancelled by user	mq6be5rmrbimwe1zyd8	A06
2480	b20643cf	AGV02	go_charge	\N	cancelled	2026-06-09 14:26:19.101341+07	2026-06-09 14:26:19.101341+07	2026-06-09 14:26:31.842778+07	force-cancelled by user	mq6bg63n99qiep8xacu	Sạc Pin
2474	9ff0c910	AGV02	go_to	19	completed	2026-06-09 14:24:45.413156+07	2026-06-09 14:24:45.413156+07	2026-06-09 14:25:09.296696+07		mq6be5rmrbimwe1zyd8	A06
2470	597c7fe9	AGV01	go_to	17	completed	2026-06-09 14:24:05.019896+07	2026-06-09 14:24:51.73794+07	2026-06-09 14:25:25.365025+07	lifecycle:picking:confirmed	mq6bdajbqs1nemhlqw	A06
2478	9cafe161	AGV01	go_charge	\N	completed	2026-06-09 14:25:25.380859+07	2026-06-09 14:25:41.384642+07	2026-06-09 14:27:34.814619+07	charge_arrived	mq6bdajbqs1nemhlqw	A06
2476	cd7eaf9f	AGV02	go_to	17	cancelled	2026-06-09 14:24:45.4564+07	\N	2026-06-09 14:25:57.440274+07	cancelled by user	mq6be5rmrbimwe1zyd8	A06
2477	d73cfda0	AGV02	go_charge	\N	cancelled	2026-06-09 14:24:45.4564+07	\N	2026-06-09 14:25:57.440274+07	cancelled by user	mq6be5rmrbimwe1zyd8	A06
2479	bfac92a9	AGV02	go_charge	\N	cancelled	2026-06-09 14:26:03.585406+07	2026-06-09 14:26:03.585406+07	2026-06-09 14:26:11.805887+07	force-cancelled by user	mq6bfu47welur7065fi	Sạc Pin
2472	e57f6826	AGV01	go_to	17	completed	2026-06-09 14:24:16.824147+07	2026-06-09 14:28:29.965294+07	2026-06-09 14:30:13.777833+07	lifecycle:picking:confirmed	mq6bdjpabm40wa7t3of	A06
2473	e63f0c01	AGV01	go_charge	\N	completed	2026-06-09 14:24:16.830582+07	2026-06-09 14:30:13.777833+07	2026-06-09 14:30:29.673195+07		mq6bdjpabm40wa7t3of	A06
2482	fac1e142	AGV02	go_to	19	cancelled	2026-06-09 14:28:07.831008+07	\N	2026-06-09 14:31:09.442701+07	cancelled by user	mq6bihxdqzvl6ckjvkc	A06
2483	894b0a48	AGV02	go_to	17	cancelled	2026-06-09 14:28:07.912915+07	\N	2026-06-09 14:31:09.442701+07	cancelled by user	mq6bihxdqzvl6ckjvkc	A06
2481	e439f24b	AGV02	go_to	19	cancelled	2026-06-09 14:28:07.759371+07	2026-06-09 14:28:07.759371+07	2026-06-09 14:31:09.442701+07	force-cancelled by user	mq6bihxdqzvl6ckjvkc	A06
2484	56cffef2	AGV02	go_charge	\N	cancelled	2026-06-09 14:28:07.914697+07	\N	2026-06-09 14:31:09.442701+07	cancelled by user	mq6bihxdqzvl6ckjvkc	A06
2485	12035054	AGV01	go_charge	\N	completed	2026-06-09 14:30:13.793357+07	2026-06-09 14:30:29.675199+07	2026-06-09 14:31:55.190388+07	charge_arrived	mq6bdjpabm40wa7t3of	A06
2488	b0214815	AGV01	go_charge	\N	completed	2026-06-11 08:25:53.185001+07	2026-06-11 08:27:53.756385+07	2026-06-11 09:08:54.408879+07		mq8tgcpp1pnibvrupn4j	A06
2489	0fe888e8	AGV02	go_to	19	completed	2026-06-11 08:26:19.102953+07	2026-06-11 08:26:19.101958+07	2026-06-11 08:26:48.645564+07		mq8tgwr6sl9exx1843	A06
2491	1eff34bb	AGV02	go_to	17	completed	2026-06-11 08:26:19.128955+07	2026-06-11 08:27:31.003909+07	2026-06-11 08:27:48.274905+07		mq8tgwr6sl9exx1843	A06
2825	3e7758f6	AGV01	go_to	5	completed	2026-06-15 11:39:00.356164+07	2026-06-15 11:39:00.359262+07	2026-06-15 11:40:12.814306+07	lifecycle:picking:confirmed	mqeq2e99a7k13fe8jm6	A06
2487	a6848f76	AGV01	go_to	17	completed	2026-06-11 08:25:53.182997+07	2026-06-11 08:26:34.330025+07	2026-06-11 08:27:53.755382+07	lifecycle:picking:confirmed	mq8tgcpp1pnibvrupn4j	A06
2493	860e9317	AGV02	go_to	17	completed	2026-06-11 08:27:31.019196+07	2026-06-11 08:27:48.276908+07	2026-06-11 08:28:04.68018+07		mq8tgwr6sl9exx1843	A06
3304	3300373b	AGV01	go_charge	\N	cancelled	2026-06-17 15:17:12.209047+07	\N	2026-06-17 15:18:13.524452+07	cancelled by user	mqhsqv1erceejbo0cm	Sạc Pin
2826	9f46ffa2	AGV02	go_charge	\N	completed	2026-06-15 11:39:36.801322+07	2026-06-15 11:40:37.662422+07	2026-06-15 11:41:30.259464+07	charge_arrived	mqeq2j9oggp54vve77m	A06
2912	9617573a	AGV02	go_to	19	completed	2026-06-16 09:01:18.256404+07	2026-06-16 09:01:18.256393+07	2026-06-16 09:01:50.262699+07		mqfzx5tha60osk3utge	A06
3098	88f7ce14	AGV01	go_to	17	completed	2026-06-16 13:25:48.163857+07	2026-06-16 14:02:02.311796+07	2026-06-16 14:02:39.035033+07	lifecycle:picking:confirmed	mqg9db1mma8mrrvp1aa	A05
2913	736f3c5b	AGV02	go_to	19	completed	2026-06-16 09:01:18.264118+07	2026-06-16 09:01:50.264221+07	2026-06-16 09:01:50.425653+07	dest_wait	mqfzx5tha60osk3utge	A06
2916	3923b320	AGV02	go_to	19	completed	2026-06-16 09:02:00.498122+07	2026-06-16 09:02:00.498119+07	2026-06-16 09:02:20.562698+07	lifecycle:picking:confirmed	mqfzx5tha60osk3utge	dest_retry
2911	d5a3c1f9	AGV01	go_charge	\N	completed	2026-06-16 09:01:08.72266+07	2026-06-16 09:02:16.513889+07	2026-06-16 09:02:31.743714+07		mqfzwyf1os41n68iyo	A06
2915	4ae452d7	AGV02	go_charge	\N	completed	2026-06-16 09:01:18.277789+07	2026-06-16 09:03:49.880342+07	2026-06-16 09:04:04.259265+07		mqfzx5tha60osk3utge	A06
3169	5771cf6d	AGV02	go_charge	\N	queued	2026-06-16 14:33:11.324683+07	\N	\N	\N	mqgbryrczuw7o3qrha	A02
3161	f873b76d	AGV01	go_to	19	completed	2026-06-16 14:32:55.331362+07	2026-06-16 14:32:55.331362+07	2026-06-16 14:33:34.212227+07	event:continue	mqgbrmgwpqnxrwntcjm	A02
2970	46db61ba	AGV02	go_to	19	completed	2026-06-16 09:50:12.53838+07	2026-06-16 09:50:24.776968+07	2026-06-16 09:50:46.016253+07		mqg1o1wl6h93q5wbixm	A02
2967	3d20b433	AGV01	go_to	17	completed	2026-06-16 09:50:00.927418+07	2026-06-16 09:50:33.425198+07	2026-06-16 09:50:54.295468+07	lifecycle:picking:confirmed	mqg1nst13z14xqfi246	A02
2972	442de18d	AGV02	go_to	18	cancelled	2026-06-16 09:50:12.574914+07	\N	2026-06-16 10:04:42.061129+07	cancelled by user	mqg1o1wl6h93q5wbixm	A02
3226	021df72c	AGV02	go_charge	\N	completed	2026-06-16 16:26:50.278674+07	2026-06-16 16:31:13.583682+07	2026-06-16 16:31:28.218642+07		mqgfu4bc6d4cjdmkuvc	A05
3040	7b2f45a7	AGV01	go_to	96	completed	2026-06-16 11:12:31.056364+07	2026-06-16 11:12:42.937529+07	2026-06-16 11:13:02.165808+07		mqg4ip6rvwvjk57emj	A05
3043	4d65a03c	AGV01	go_to	9	completed	2026-06-16 11:13:21.016228+07	2026-06-16 11:13:21.018421+07	2026-06-16 11:13:34.227414+07		mqg4ip6rvwvjk57emj	A05
3036	c5021928	AGV02	go_to	19	completed	2026-06-16 11:10:16.338962+07	2026-06-16 11:10:16.338957+07	2026-06-16 11:13:45.372599+07	lifecycle:picking:confirmed	mqg4j0j3qqi1ob33vfc	A02
3038	7da6d981	AGV02	go_to	16	completed	2026-06-16 11:10:16.403822+07	2026-06-16 11:14:05.426593+07	2026-06-16 11:15:52.825857+07	lifecycle:picking:confirmed	mqg4j0j3qqi1ob33vfc	A02
3163	e5ba1ed6	AGV01	go_to	15	completed	2026-06-16 14:32:55.373628+07	2026-06-16 14:34:21.334812+07	2026-06-16 14:35:02.019075+07		mqgbrmgwpqnxrwntcjm	A02
3042	598e63e9	AGV01	go_to	96	completed	2026-06-16 11:13:02.195011+07	2026-06-16 11:16:52.819361+07	2026-06-16 11:17:16.125348+07	off_route	mqg4ip6rvwvjk57emj	A05
3291	1448a3ff	AGV02	go_to	5	completed	2026-06-17 15:15:07.147592+07	2026-06-17 15:15:07.149951+07	2026-06-17 15:15:24.201799+07	off_route	mqhsowjvw2nb4s34tdt	Sạc Pin
3047	c9162df3	AGV01	go_to	19	completed	2026-06-16 11:17:16.124368+07	2026-06-16 11:17:16.12682+07	2026-06-16 11:18:47.248526+07	lifecycle:picking:confirmed	mqg4ip6rvwvjk57emj	A05
3046	1db02398	AGV01	go_to	96	completed	2026-06-16 11:16:52.851272+07	2026-06-16 11:18:47.248643+07	2026-06-16 11:18:58.987206+07		mqg4ip6rvwvjk57emj	A05
3173	e51a33aa	AGV02	go_to	18	queued	2026-06-16 14:35:18.81125+07	\N	\N	\N	mqgbryrczuw7o3qrha	A02
3048	9960ed9e	AGV01	go_to	96	completed	2026-06-16 11:18:47.270734+07	2026-06-16 11:18:58.987625+07	2026-06-16 11:23:07.160149+07	lifecycle:picking:confirmed	mqg4ip6rvwvjk57emj	A05
3035	46f9ad38	AGV01	go_to	17	completed	2026-06-16 11:10:01.80592+07	2026-06-16 11:23:07.160225+07	2026-06-16 11:23:47.449371+07	lifecycle:picking:confirmed	mqg4ip6rvwvjk57emj	A05
3103	5725d585	AGV01	go_to	18	cancelled	2026-06-16 13:26:07.226061+07	\N	2026-06-16 13:26:19.13924+07	cancelled by user	mqg9dpsqq4qrrx9oib	A02
3172	df3fd75b	AGV02	go_to	18	completed	2026-06-16 14:35:00.778892+07	2026-06-16 14:35:14.986732+07	2026-06-16 14:35:34.445566+07	off_route	mqgbryrczuw7o3qrha	A02
3096	dd708a34	AGV01	go_to	19	completed	2026-06-16 13:25:48.149262+07	2026-06-16 13:26:51.560488+07	2026-06-16 13:26:51.57264+07	dest_wait	mqg9db1mma8mrrvp1aa	A05
3107	b5c26542	AGV02	go_to	18	cancelled	2026-06-16 13:26:47.535574+07	\N	2026-06-16 13:58:33.249856+07	cancelled by user	mqg9ekwqmgwzmof7bed	A02
3174	a5222be1	AGV02	go_to	16	running	2026-06-16 14:35:34.443569+07	2026-06-16 14:35:34.445566+07	\N		mqgbryrczuw7o3qrha	A02
3227	48c5fa7a	AGV02	go_to	19	completed	2026-06-16 16:26:53.248551+07	2026-06-16 16:32:11.790703+07	2026-06-16 16:32:11.800708+07	pickup_already_done	mqgfu4bc6d4cjdmkuvc	dest_retry
3215	7b625eeb	AGV01	go_to	18	completed	2026-06-16 16:26:30.922972+07	2026-06-16 16:27:02.800745+07	2026-06-16 16:27:20.003897+07	event:continue	mqgftpa7owxsvi8mh7	A05
3222	e853c3c5	AGV02	go_to	16	completed	2026-06-16 16:26:50.26961+07	2026-06-16 16:27:35.750095+07	2026-06-16 16:28:25.789489+07	event:continue	mqgfu4bc6d4cjdmkuvc	A05
3228	b724089e	AGV02	go_to	17	completed	2026-06-16 16:28:27.654294+07	2026-06-16 16:28:44.041112+07	2026-06-16 16:29:14.690402+07	event:continue	mqgfu4bc6d4cjdmkuvc	A05
3277	a85b3cfe	AGV02	go_to	19	completed	2026-06-17 15:07:13.341269+07	2026-06-17 15:07:13.341269+07	2026-06-17 15:07:35.679529+07		mqhsfl2pa78j54i9pku	A05
3224	3716d549	AGV02	go_to	15	completed	2026-06-16 16:26:50.273666+07	2026-06-16 16:29:14.691622+07	2026-06-16 16:29:29.234682+07		mqgfu4bc6d4cjdmkuvc	A05
3217	27e16c3c	AGV01	go_charge	\N	completed	2026-06-16 16:26:30.935007+07	2026-06-16 16:29:22.038884+07	2026-06-16 16:30:52.89345+07	charge_arrived	mqgftpa7owxsvi8mh7	A05
3299	c3a78fec	AGV01	go_charge	\N	completed	2026-06-17 15:15:59.366882+07	2026-06-17 15:15:59.366882+07	2026-06-17 15:16:13.964907+07		mqhsqv1erceejbo0cm	Sạc Pin
3279	7ec7431c	AGV02	go_to	16	completed	2026-06-17 15:07:13.469502+07	2026-06-17 15:08:02.407531+07	2026-06-17 15:09:28.151814+07	lifecycle:picking:confirmed	mqhsfl2pa78j54i9pku	A05
3286	a8fa89d1	AGV02	go_to	15	cancelled	2026-06-17 15:10:55.933709+07	2026-06-17 15:11:15.849938+07	2026-06-17 15:14:01.078921+07	force-cancelled by user	mqhsfl2pa78j54i9pku	A05
3298	03517aaf	AGV02	go_to	19	cancelled	2026-06-17 15:15:56.481406+07	\N	2026-06-17 15:16:21.256438+07	cancelled by user	mqhsowjvw2nb4s34tdt	Sạc Pin
3276	3f9e9b96	AGV01	go_to	16	cancelled	2026-06-17 15:06:48.862414+07	2026-06-17 15:08:55.702694+07	2026-06-17 15:15:48.88275+07	force-cancelled by user	mqhsf1zpsqjkenlbmq8	A05
3295	9a20924e	AGV02	go_to	4	completed	2026-06-17 15:15:40.898305+07	2026-06-17 15:15:40.899295+07	2026-06-17 15:15:56.455386+07	off_route	mqhsowjvw2nb4s34tdt	Sạc Pin
3294	28cb0712	AGV02	go_to	18	cancelled	2026-06-17 15:15:24.219679+07	\N	2026-06-17 15:16:21.256438+07	cancelled by user	mqhsowjvw2nb4s34tdt	Sạc Pin
3290	5b4b888e	AGV02	go_to	13	cancelled	2026-06-17 15:14:51.105206+07	\N	2026-06-17 15:16:21.256438+07	cancelled by user	mqhsowjvw2nb4s34tdt	Sạc Pin
3300	9e4fcdfc	AGV01	go_charge	\N	completed	2026-06-17 15:15:59.381278+07	2026-06-17 15:16:13.9658+07	2026-06-17 15:17:12.194484+07	off_route	mqhsqv1erceejbo0cm	Sạc Pin
3340	baaf82cc	AGV02	go_charge	\N	cancelled	2026-06-17 15:39:09.651628+07	\N	2026-06-17 15:39:19.601807+07	cancelled by user	mqhtij70mgu93d4afgo	yield_resume
3387	9302f073	AGV02	go_to	19	completed	2026-06-17 16:38:29.806346+07	2026-06-17 16:38:57.677208+07	2026-06-17 16:38:57.705874+07	dest_wait	mqhvoyr9beumsloftrw	A05
3394	438d1318	AGV01	go_to	15	completed	2026-06-17 16:39:30.935567+07	2026-06-17 16:39:46.492682+07	2026-06-17 16:40:31.567628+07	lifecycle:picking:confirmed	mqhvomjojv5d8mg1ys	A05
3389	27bd7203	AGV02	go_to	18	completed	2026-06-17 16:38:29.877933+07	2026-06-17 16:41:04.610083+07	2026-06-17 16:41:19.324272+07		mqhvoyr9beumsloftrw	A05
3384	963909b0	AGV01	go_to	18	completed	2026-06-17 16:38:14.420964+07	2026-06-17 16:40:31.567628+07	2026-06-17 16:41:15.886895+07	lifecycle:picking:confirmed	mqhvomjojv5d8mg1ys	A05
3396	291a9feb	AGV02	go_to	8	completed	2026-06-17 16:41:04.665703+07	2026-06-17 16:41:19.327279+07	2026-06-17 16:41:19.339273+07	already_at_dest	mqhvoyr9beumsloftrw	A05
2486	78f69db1	AGV01	go_to	19	completed	2026-06-11 08:25:53.134098+07	2026-06-11 08:25:53.134098+07	2026-06-11 08:26:34.329027+07	lifecycle:picking:confirmed	mq8tgcpp1pnibvrupn4j	A06
2516	67be417e	AGV02	go_to	17	completed	2026-06-12 16:05:26.318385+07	2026-06-12 16:06:21.991919+07	2026-06-12 16:06:37.874304+07		mqapb6z66fp4yof3vek	A06
2490	25748a0e	AGV02	go_to	19	completed	2026-06-11 08:26:19.111951+07	2026-06-11 08:26:48.646564+07	2026-06-11 08:27:31.003909+07	lifecycle:picking:confirmed	mq8tgwr6sl9exx1843	A06
2527	04bdfea7	AGV02	go_to	19	completed	2026-06-12 16:15:34.340317+07	2026-06-12 16:16:11.41479+07	2026-06-12 16:16:35.03155+07	lifecycle:picking:confirmed	mqapo85hx9wigqrq9ta	A06
2494	a568711a	AGV02	go_to	17	cancelled	2026-06-11 08:27:48.287423+07	2026-06-11 08:28:04.68018+07	2026-06-11 09:06:34.985212+07	force-cancelled by user	mq8tgwr6sl9exx1843	A06
2492	95c00178	AGV02	go_charge	\N	cancelled	2026-06-11 08:26:19.12996+07	\N	2026-06-11 09:06:34.998206+07	cancelled by user	mq8tgwr6sl9exx1843	A06
2496	2339a79f	AGV02	go_charge	\N	cancelled	2026-06-11 09:06:44.740216+07	2026-06-11 09:06:44.740216+07	2026-06-11 09:07:00.237248+07	force-cancelled by user	mq8uwwdw8cat1wwu4k7	Sạc Pin
2497	8c848908	AGV02	go_charge	\N	cancelled	2026-06-11 09:06:44.866907+07	\N	2026-06-11 09:07:00.237248+07	cancelled by user	mq8uwwdw8cat1wwu4k7	Sạc Pin
2495	8ed1b726	AGV01	go_charge	\N	cancelled	2026-06-11 08:27:53.774386+07	2026-06-11 09:08:54.40982+07	2026-06-11 09:09:58.273696+07	force-cancelled by user	mq8tgcpp1pnibvrupn4j	A06
2498	70121386	AGV01	go_charge	\N	cancelled	2026-06-11 09:10:07.948678+07	2026-06-11 09:10:07.948678+07	2026-06-11 09:10:38.953427+07	force-cancelled by user	mq8v196taol9pyyfv1	Sạc Pin
2499	2afe9fcd	AGV01	go_charge	\N	completed	2026-06-11 09:10:46.416961+07	2026-06-11 09:10:46.416961+07	2026-06-11 09:11:02.309259+07		mq8v22vhxjzwlrd2kk8	Sạc Pin
2512	01a28950	AGV01	go_to	17	completed	2026-06-12 16:05:13.341731+07	2026-06-12 16:05:47.766701+07	2026-06-12 16:06:55.701809+07	lifecycle:picking:confirmed	mqapawxnqnx7by8iuy	A06
2500	4d206932	AGV01	go_charge	\N	completed	2026-06-11 09:10:46.430854+07	2026-06-11 09:11:02.31126+07	2026-06-11 12:45:51.218091+07	off_route	mq8v22vhxjzwlrd2kk8	Sạc Pin
2501	af5c1042	AGV01	go_charge	14	completed	2026-06-11 12:45:51.210693+07	2026-06-11 12:45:51.223104+07	2026-06-11 12:45:56.677182+07	charge_arrived	mq8v22vhxjzwlrd2kk8	Sạc Pin
2505	6d04bbe0	AGV02	go_to	17	queued	2026-06-12 14:31:10.016325+07	\N	\N	\N	mqalxye1ez3sdrmlg4q	A05
2506	0edcf1c6	AGV02	go_to	96	queued	2026-06-12 14:31:10.021329+07	\N	\N	\N	mqalxye1ez3sdrmlg4q	A05
2507	6620a702	AGV02	go_charge	\N	queued	2026-06-12 14:31:10.023326+07	\N	\N	\N	mqalxye1ez3sdrmlg4q	A05
2502	5e59844c	AGV02	go_to	64	completed	2026-06-12 14:31:09.953326+07	2026-06-12 14:31:09.953326+07	2026-06-12 14:31:59.804792+07	lifecycle:picking:confirmed	mqalxye1ez3sdrmlg4q	A05
2519	9a1cc4a6	AGV02	go_to	17	completed	2026-06-12 16:06:22.006216+07	2026-06-12 16:06:37.876706+07	2026-06-12 16:06:55.816434+07		mqapb6z66fp4yof3vek	A06
2529	641d096d	AGV02	go_to	17	completed	2026-06-12 16:15:34.490879+07	2026-06-12 16:16:35.031653+07	2026-06-12 16:16:53.223356+07		mqapo85hx9wigqrq9ta	A06
2503	1de59e4b	AGV02	go_to	19	completed	2026-06-12 14:31:10.00844+07	2026-06-12 14:31:59.805817+07	2026-06-12 14:32:12.598175+07	lifecycle:picking:confirmed	mqalxye1ez3sdrmlg4q	A05
2504	b918ca3b	AGV02	go_to	69	completed	2026-06-12 14:31:10.009388+07	2026-06-12 14:32:12.603174+07	2026-06-12 14:32:23.904369+07		mqalxye1ez3sdrmlg4q	A05
2535	ef7cabe3	AGV01	go_to	19	completed	2026-06-12 16:39:10.753391+07	2026-06-12 16:39:10.753372+07	2026-06-12 16:39:44.946381+07	lifecycle:picking:confirmed	mqaqil1mx39etu657j8	A06
2509	2d7ea83a	AGV02	go_to	69	completed	2026-06-12 14:32:12.831854+07	2026-06-12 14:32:23.905369+07	2026-06-12 14:33:09.694411+07	lifecycle:picking:confirmed	mqalxye1ez3sdrmlg4q	A05
2508	b1b45535	AGV02	go_to	16	running	2026-06-12 14:31:10.011332+07	2026-06-12 14:33:09.699428+07	\N		mqalxye1ez3sdrmlg4q	A05
2510	d9dcfcec	AGV02	go_charge	\N	cancelled	2026-06-12 16:03:29.024488+07	2026-06-12 16:03:29.02448+07	2026-06-12 16:03:52.498219+07	force-cancelled by user	mqap8oh6tfkmwude9q	Sạc Pin
2520	332f370b	AGV02	go_to	17	completed	2026-06-12 16:06:37.892583+07	2026-06-12 16:06:55.817079+07	2026-06-12 16:09:21.790287+07	lifecycle:picking:confirmed	mqapb6z66fp4yof3vek	A06
2514	8fe93670	AGV02	go_to	19	completed	2026-06-12 16:05:26.288581+07	2026-06-12 16:05:26.288552+07	2026-06-12 16:05:43.315702+07		mqapb6z66fp4yof3vek	A06
2511	49780c27	AGV01	go_to	19	completed	2026-06-12 16:05:13.271828+07	2026-06-12 16:05:13.271821+07	2026-06-12 16:05:47.766431+07	lifecycle:picking:confirmed	mqapawxnqnx7by8iuy	A06
2515	8af9bc3b	AGV02	go_to	19	completed	2026-06-12 16:05:26.299764+07	2026-06-12 16:05:43.316195+07	2026-06-12 16:06:02.657763+07		mqapb6z66fp4yof3vek	A06
2518	96098f51	AGV02	go_to	19	completed	2026-06-12 16:05:43.460248+07	2026-06-12 16:06:02.658083+07	2026-06-12 16:06:21.991824+07	lifecycle:picking:confirmed	mqapb6z66fp4yof3vek	A06
2530	4a9ff5f5	AGV02	go_to	17	completed	2026-06-12 16:16:35.043393+07	2026-06-12 16:16:53.225908+07	2026-06-12 16:17:11.20777+07		mqapo85hx9wigqrq9ta	A06
2517	8fba1bff	AGV02	go_charge	\N	completed	2026-06-12 16:05:26.319326+07	2026-06-12 16:09:21.790394+07	2026-06-12 16:09:36.055374+07		mqapb6z66fp4yof3vek	A06
2521	361d080e	AGV02	go_charge	\N	completed	2026-06-12 16:09:21.817972+07	2026-06-12 16:09:36.05552+07	2026-06-12 16:09:53.774365+07	charge_arrived	mqapb6z66fp4yof3vek	A06
2513	90ac3b72	AGV01	go_charge	\N	completed	2026-06-12 16:05:13.343838+07	2026-06-12 16:06:55.702022+07	2026-06-12 16:10:24.805437+07	event:continue	mqapawxnqnx7by8iuy	A06
2522	06839ff5	AGV01	go_charge	\N	cancelled	2026-06-12 16:13:39.586233+07	2026-06-12 16:13:39.586227+07	2026-06-12 16:13:59.2742+07	force-cancelled by user	mqaplrm53dvzbigrp78	Sạc Pin
2523	838eab87	AGV01	go_to	19	completed	2026-06-12 16:15:25.478616+07	2026-06-12 16:15:25.47861+07	2026-06-12 16:16:01.031832+07	lifecycle:picking:confirmed	mqapo1b0c1k3pikkz55	A06
2533	d6f46354	AGV02	go_charge	\N	completed	2026-06-12 16:18:07.890049+07	2026-06-12 16:18:22.240545+07	2026-06-12 16:19:10.547906+07	charge_arrived	mqapo85hx9wigqrq9ta	A06
2526	18615377	AGV02	go_to	19	completed	2026-06-12 16:15:34.33626+07	2026-06-12 16:15:34.336252+07	2026-06-12 16:16:11.413356+07		mqapo85hx9wigqrq9ta	A06
2534	1955e845	AGV01	go_charge	\N	completed	2026-06-12 16:19:06.193186+07	2026-06-12 16:19:06.193173+07	2026-06-12 16:20:11.793915+07	charge_arrived	mqapsrmeof9xin1vkd	Sạc Pin
2531	429ef42d	AGV02	go_to	17	completed	2026-06-12 16:16:53.25219+07	2026-06-12 16:17:11.208397+07	2026-06-12 16:17:11.230169+07	dest_wait	mqapo85hx9wigqrq9ta	A06
2524	b0e78474	AGV01	go_to	17	completed	2026-06-12 16:15:25.523368+07	2026-06-12 16:16:01.032041+07	2026-06-12 16:17:11.882386+07	lifecycle:picking:confirmed	mqapo1b0c1k3pikkz55	A06
2525	fa279be5	AGV01	go_charge	\N	completed	2026-06-12 16:15:25.526339+07	2026-06-12 16:17:11.882456+07	2026-06-12 16:17:59.91462+07	event:continue	mqapo1b0c1k3pikkz55	A06
2532	4af471ee	AGV02	go_to	17	completed	2026-06-12 16:17:20.470786+07	2026-06-12 16:17:20.470782+07	2026-06-12 16:18:07.859368+07	event:continue	mqapo85hx9wigqrq9ta	dest_retry
2539	b11cdeee	AGV02	go_to	19	completed	2026-06-12 16:39:21.435036+07	2026-06-12 16:39:54.054652+07	2026-06-12 16:40:32.910178+07	lifecycle:picking:confirmed	mqaqitayl7zbgeib1ui	A06
2528	759fa2e6	AGV02	go_charge	\N	completed	2026-06-12 16:15:34.492905+07	2026-06-12 16:18:07.859735+07	2026-06-12 16:18:22.240017+07		mqapo85hx9wigqrq9ta	A06
2538	01d2ade9	AGV02	go_to	19	completed	2026-06-12 16:39:21.427899+07	2026-06-12 16:39:21.427893+07	2026-06-12 16:39:54.054305+07		mqaqitayl7zbgeib1ui	A06
2536	af7272ac	AGV01	go_charge	\N	completed	2026-06-12 16:39:11.034938+07	2026-06-12 16:40:25.014779+07	2026-06-12 16:40:40.090831+07		mqaqil1mx39etu657j8	A06
2541	e391ff61	AGV02	go_to	17	cancelled	2026-06-12 16:39:21.592052+07	2026-06-12 16:40:32.910331+07	2026-06-12 16:49:16.791935+07	force-cancelled by user	mqaqitayl7zbgeib1ui	A06
2537	cf25fa03	AGV01	go_to	17	completed	2026-06-12 16:39:11.032202+07	2026-06-12 16:39:44.946536+07	2026-06-12 16:40:25.014488+07	lifecycle:picking:confirmed	mqaqil1mx39etu657j8	A06
2540	21e298d2	AGV02	go_charge	\N	cancelled	2026-06-12 16:39:21.594441+07	\N	2026-06-12 16:49:16.792074+07	cancelled by user	mqaqitayl7zbgeib1ui	A06
2543	2a685d61	AGV02	go_charge	\N	completed	2026-06-12 16:49:33.082336+07	2026-06-12 16:49:33.082318+07	2026-06-12 16:49:55.577967+07		mqaqvx99sujcojyxim	Sạc Pin
2542	d0c9f019	AGV01	go_charge	\N	cancelled	2026-06-12 16:40:25.035168+07	2026-06-12 16:40:40.091439+07	2026-06-12 16:49:25.244835+07	force-cancelled by user	mqaqil1mx39etu657j8	A06
2546	e43ec2d8	AGV01	go_charge	\N	completed	2026-06-12 16:50:27.355416+07	2026-06-12 16:50:27.3554+07	2026-06-12 16:50:41.69338+07		mqaqx356fdzdvamog8p	Sạc Pin
2545	fb02b8dd	AGV01	go_charge	\N	cancelled	2026-06-12 16:49:53.836271+07	2026-06-12 16:49:53.836258+07	2026-06-12 16:50:22.475618+07	force-cancelled by user	mqaqwd9uryyeuwcadns	Sạc Pin
2547	95c9efb5	AGV01	go_charge	\N	completed	2026-06-12 16:50:27.38605+07	2026-06-12 16:50:41.694071+07	2026-06-12 16:51:38.741528+07	charge_arrived	mqaqx356fdzdvamog8p	Sạc Pin
2544	a33a3986	AGV02	go_charge	\N	completed	2026-06-12 16:49:33.106976+07	2026-06-12 16:49:55.578566+07	2026-06-12 16:50:30.181997+07	charge_arrived	mqaqvx99sujcojyxim	Sạc Pin
2559	27b9f9ab	AGV02	go_charge	\N	completed	2026-06-12 16:53:49.326084+07	2026-06-12 16:54:12.37008+07	2026-06-12 16:55:02.118179+07	charge_arrived	mqaqz3q1pnrpbjuwsj	A06
2827	fc6d2f2f	AGV01	go_to	19	completed	2026-06-15 11:42:37.173694+07	2026-06-15 11:42:37.17366+07	2026-06-15 11:43:08.144344+07	lifecycle:picking:confirmed	mqeq8rf9l5qzr1bowyq	A06
3292	d1529a8a	AGV02	go_to	5	cancelled	2026-06-17 15:15:07.30756+07	\N	2026-06-17 15:16:21.256438+07	cancelled by user	mqhsowjvw2nb4s34tdt	Sạc Pin
2831	fcdcb17d	AGV02	go_to	19	completed	2026-06-15 11:42:43.066185+07	2026-06-15 11:43:19.844886+07	2026-06-15 11:44:00.13469+07	lifecycle:picking:confirmed	mqeq8vzlt7bftsfe1h	A06
3166	37428ea6	AGV02	go_to	19	completed	2026-06-16 14:33:11.302619+07	2026-06-16 14:33:24.385746+07	2026-06-16 14:33:51.061468+07		mqgbryrczuw7o3qrha	A02
3170	8b08d938	AGV02	go_to	19	completed	2026-06-16 14:33:24.393787+07	2026-06-16 14:33:51.062624+07	2026-06-16 14:34:15.200964+07	event:continue	mqgbryrczuw7o3qrha	A02
2828	983d6337	AGV01	go_charge	\N	completed	2026-06-15 11:42:37.346414+07	2026-06-15 11:44:17.462788+07	2026-06-15 11:44:50.627631+07		mqeq8rf9l5qzr1bowyq	A06
2834	092974cf	AGV02	go_to	17	completed	2026-06-15 11:44:00.148661+07	2026-06-15 11:44:16.110325+07	2026-06-15 11:46:12.954705+07	off_route	mqeq8vzlt7bftsfe1h	A06
2837	172fbe32	AGV02	go_to	18	completed	2026-06-15 11:46:12.95435+07	2026-06-15 11:46:12.955035+07	2026-06-15 11:46:19.247959+07	off_route	mqeq8vzlt7bftsfe1h	A06
3162	8751aacc	AGV01	go_to	17	completed	2026-06-16 14:32:55.369079+07	2026-06-16 14:33:34.214633+07	2026-06-16 14:34:21.333756+07	event:continue	mqgbrmgwpqnxrwntcjm	A02
2833	79047b08	AGV02	go_charge	\N	completed	2026-06-15 11:42:43.080884+07	2026-06-15 11:47:57.901358+07	2026-06-15 11:48:12.350128+07		mqeq8vzlt7bftsfe1h	A06
2917	3225b114	AGV01	go_charge	\N	completed	2026-06-16 09:02:16.538254+07	2026-06-16 09:02:31.744054+07	2026-06-16 09:04:23.922834+07	charge_arrived	mqfzwyf1os41n68iyo	A06
2969	82b3cb65	AGV02	go_to	19	completed	2026-06-16 09:50:12.533648+07	2026-06-16 09:50:12.533642+07	2026-06-16 09:50:24.776746+07		mqg1o1wl6h93q5wbixm	A02
3171	ac3692fe	AGV01	go_to	15	running	2026-06-16 14:34:21.363383+07	2026-06-16 14:35:02.019075+07	\N		mqgbrmgwpqnxrwntcjm	A02
2971	7f9a5524	AGV02	go_to	16	cancelled	2026-06-16 09:50:12.573435+07	2026-06-16 09:51:05.90339+07	2026-06-16 10:04:42.06093+07	force-cancelled by user	mqg1o1wl6h93q5wbixm	A02
2973	a44139dd	AGV02	go_charge	\N	cancelled	2026-06-16 09:50:12.576585+07	\N	2026-06-16 10:04:42.061129+07	cancelled by user	mqg1o1wl6h93q5wbixm	A02
2975	5ed8c7d5	AGV01	go_to	15	cancelled	2026-06-16 09:50:54.358919+07	2026-06-16 09:51:09.489953+07	2026-06-16 10:04:48.009075+07	force-cancelled by user	mqg1nst13z14xqfi246	A02
2968	5e3db46d	AGV01	go_charge	\N	cancelled	2026-06-16 09:50:00.929845+07	\N	2026-06-16 10:04:48.009244+07	cancelled by user	mqg1nst13z14xqfi246	A02
2979	a257119a	AGV01	go_charge	\N	completed	2026-06-16 10:05:55.615071+07	2026-06-16 10:05:55.615063+07	2026-06-16 10:06:10.255427+07		mqg289lzbfl8rz6d9x6	Sạc Pin
3168	6691fe58	AGV02	go_to	18	completed	2026-06-16 14:33:11.323735+07	2026-06-16 14:35:00.752212+07	2026-06-16 14:35:14.985735+07		mqgbryrczuw7o3qrha	A02
2980	7d8ab255	AGV01	go_charge	\N	completed	2026-06-16 10:05:55.673087+07	2026-06-16 10:06:10.256664+07	2026-06-16 10:07:23.869933+07	charge_arrived	mqg289lzbfl8rz6d9x6	Sạc Pin
3049	ae534ade	AGV01	go_to	15	completed	2026-06-16 11:23:47.481005+07	2026-06-16 11:24:02.679027+07	2026-06-16 11:24:34.92551+07	lifecycle:picking:confirmed	mqg4ip6rvwvjk57emj	A05
3060	dce70dd5	AGV01	go_to	18	completed	2026-06-16 11:28:18.397834+07	2026-06-16 11:28:18.401597+07	2026-06-16 11:28:33.445494+07	off_route	mqg4ip6rvwvjk57emj	A05
3059	5cc4736e	AGV01	go_to	4	cancelled	2026-06-16 11:27:57.897572+07	\N	2026-06-16 11:31:09.740015+07	cancelled by user	mqg4ip6rvwvjk57emj	A05
3062	7fde72f3	AGV01	go_to	5	cancelled	2026-06-16 11:28:33.445128+07	2026-06-16 11:28:33.44581+07	2026-06-16 11:31:09.739433+07	force-cancelled by user	mqg4ip6rvwvjk57emj	A05
3061	63a65b0f	AGV01	go_to	18	cancelled	2026-06-16 11:28:18.424804+07	\N	2026-06-16 11:31:09.740015+07	cancelled by user	mqg4ip6rvwvjk57emj	A05
3101	4e88bc44	AGV01	go_to	19	cancelled	2026-06-16 13:26:07.223276+07	\N	2026-06-16 13:26:17.503755+07	cancelled by user	mqg9dpsqq4qrrx9oib	A02
3100	6a75b854	AGV01	go_to	69	completed	2026-06-16 13:25:48.153673+07	2026-06-16 14:00:13.414369+07	2026-06-16 14:00:44.332594+07	lifecycle:picking:confirmed	mqg9db1mma8mrrvp1aa	A05
3386	22a8a063	AGV02	go_to	19	completed	2026-06-17 16:38:29.789818+07	2026-06-17 16:38:29.789818+07	2026-06-17 16:38:57.674213+07		mqhvoyr9beumsloftrw	A05
3223	6997127e	AGV02	go_to	17	completed	2026-06-16 16:26:50.272663+07	2026-06-16 16:28:25.791538+07	2026-06-16 16:28:44.040074+07		mqgfu4bc6d4cjdmkuvc	A05
3218	ab3e1a68	AGV01	go_to	16	completed	2026-06-16 16:26:30.925001+07	2026-06-16 16:27:43.765408+07	2026-06-16 16:29:09.360234+07	event:continue	mqgftpa7owxsvi8mh7	A05
3341	161b5742	AGV01	go_to	19	completed	2026-06-17 15:43:37.061636+07	2026-06-17 15:43:37.061636+07	2026-06-17 15:44:12.739214+07	lifecycle:picking:confirmed	mqhtqe24m1idh8dw9u	A05
3229	1a0e700f	AGV02	go_to	15	completed	2026-06-16 16:29:14.705823+07	2026-06-16 16:29:29.236522+07	2026-06-16 16:29:56.685114+07	event:continue	mqgfu4bc6d4cjdmkuvc	A05
3231	d385e767	AGV01	go_to	19	completed	2026-06-16 16:40:37.888591+07	2026-06-16 16:40:37.888591+07	2026-06-16 16:41:17.721734+07	lifecycle:picking:confirmed	mqggbuwu3cpos7vdpfs	A05
3342	7091cb30	AGV01	go_to	17	completed	2026-06-17 15:43:37.089668+07	2026-06-17 15:44:12.739214+07	2026-06-17 15:45:05.342678+07	lifecycle:picking:confirmed	mqhtqe24m1idh8dw9u	A05
3233	12360a36	AGV01	go_to	16	completed	2026-06-16 16:40:38.1613+07	2026-06-16 16:44:41.526158+07	2026-06-16 16:45:24.439722+07	lifecycle:picking:confirmed	mqggbuwu3cpos7vdpfs	A05
3293	2bf68f46	AGV02	go_to	18	completed	2026-06-17 15:15:24.200774+07	2026-06-17 15:15:24.201799+07	2026-06-17 15:15:40.899295+07	off_route	mqhsowjvw2nb4s34tdt	Sạc Pin
3297	635fdae4	AGV02	go_to	19	completed	2026-06-17 15:15:56.455386+07	2026-06-17 15:15:56.456391+07	2026-06-17 15:16:14.207662+07	off_route	mqhsowjvw2nb4s34tdt	Sạc Pin
3302	206b5352	AGV02	go_to	64	cancelled	2026-06-17 15:16:14.242952+07	\N	2026-06-17 15:16:21.256438+07	cancelled by user	mqhsowjvw2nb4s34tdt	Sạc Pin
3344	85d2e85a	AGV01	go_to	18	cancelled	2026-06-17 15:43:37.102006+07	\N	2026-06-17 15:50:47.680915+07	cancelled by user	mqhtqe24m1idh8dw9u	A05
3354	e23f5f77	AGV01	go_to	15	cancelled	2026-06-17 15:45:05.373951+07	\N	2026-06-17 15:50:47.680915+07	cancelled by user	mqhtqe24m1idh8dw9u	A05
3353	841bed13	AGV02	go_charge	\N	cancelled	2026-06-17 15:44:01.388337+07	\N	2026-06-17 15:51:01.116254+07	cancelled by user	mqhtqwszecj5hpyoiqr	A05
3355	45374fb8	AGV02	go_charge	\N	cancelled	2026-06-17 15:51:29.47906+07	2026-06-17 15:51:29.47906+07	2026-06-17 15:51:41.82793+07	force-cancelled by user	mqhu0im3gy0gqn8pcn	Sạc Pin
3391	5f3aa71d	AGV02	go_to	15	completed	2026-06-17 16:38:29.891967+07	2026-06-17 16:44:05.015199+07	2026-06-17 16:44:20.11608+07		mqhvoyr9beumsloftrw	A05
3393	265aea21	AGV02	go_to	19	completed	2026-06-17 16:39:11.372004+07	2026-06-17 16:39:11.372004+07	2026-06-17 16:39:35.002326+07	lifecycle:picking:confirmed	mqhvoyr9beumsloftrw	dest_retry
3388	23a24ae2	AGV02	go_to	16	completed	2026-06-17 16:38:29.871913+07	2026-06-17 16:39:35.002326+07	2026-06-17 16:41:04.610083+07	lifecycle:picking:confirmed	mqhvoyr9beumsloftrw	A05
3401	c7214fe7	AGV02	go_to	18	completed	2026-06-17 16:42:46.379626+07	2026-06-17 16:43:00.655828+07	2026-06-17 16:43:49.903203+07	lifecycle:picking:confirmed	mqhvoyr9beumsloftrw	yield_resume
3395	65551967	AGV02	go_to	18	completed	2026-06-17 16:41:04.63008+07	2026-06-17 16:41:19.341277+07	2026-06-17 16:41:25.212531+07	yield_siding	mqhvoyr9beumsloftrw	A05
3385	6ad86c7e	AGV01	go_to	16	completed	2026-06-17 16:38:14.434533+07	2026-06-17 16:41:15.887853+07	2026-06-17 16:42:29.870623+07	lifecycle:picking:confirmed	mqhvomjojv5d8mg1ys	A05
3402	90677ac5	AGV02	go_to	15	completed	2026-06-17 16:44:05.051598+07	2026-06-17 16:44:20.11608+07	2026-06-17 16:44:52.735382+07	lifecycle:picking:confirmed	mqhvoyr9beumsloftrw	A05
3403	af8eefd3	AGV02	go_charge	14	completed	2026-06-17 16:45:48.387724+07	2026-06-17 16:45:48.389725+07	2026-06-17 16:46:01.526878+07	off_route	mqhvoyr9beumsloftrw	A05
3408	5971c1e7	AGV02	go_to	1	cancelled	2026-06-17 16:46:10.439192+07	\N	2026-06-17 16:54:29.943938+07	cancelled by user	mqhvoyr9beumsloftrw	A05
3413	dd719144	AGV01	go_to	15	cancelled	2026-06-18 08:12:38.398093+07	\N	2026-06-18 08:40:12.398777+07	cancelled by user	mqit2a1jo8v278sc1x	A05
3441	09cbe9d1	AGV01	go_to	18	cancelled	2026-06-18 08:52:26.14706+07	\N	2026-06-18 08:53:16.637268+07	cancelled by user	mqiuhgk4zr1nj2r6ko	A02
3442	2d76ac4b	AGV02	go_to	19	completed	2026-06-18 08:53:49.974799+07	2026-06-18 08:53:49.974799+07	2026-06-18 08:54:12.190807+07		mqiuj988eyw7f3ggq4l	A02
2551	4d45be49	AGV02	go_to	19	completed	2026-06-12 16:52:01.426067+07	2026-06-12 16:52:01.426045+07	2026-06-12 16:52:13.363083+07		mqaqz3q1pnrpbjuwsj	A06
2552	5cd0877d	AGV02	go_to	19	completed	2026-06-12 16:52:01.434596+07	2026-06-12 16:52:13.364047+07	2026-06-12 16:52:13.37617+07	dest_wait	mqaqz3q1pnrpbjuwsj	A06
2548	3e64bb85	AGV01	go_to	19	completed	2026-06-12 16:51:49.806981+07	2026-06-12 16:51:49.806976+07	2026-06-12 16:52:22.837381+07	lifecycle:picking:confirmed	mqaqyure8mcir2tqtee	A06
2555	0456615e	AGV02	go_to	19	completed	2026-06-12 16:52:13.771792+07	2026-06-12 16:52:13.771786+07	2026-06-12 16:52:32.872883+07		mqaqz3q1pnrpbjuwsj	dest_retry
2554	535e6d77	AGV02	go_charge	\N	completed	2026-06-12 16:52:01.461155+07	2026-06-12 16:53:49.31009+07	2026-06-12 16:54:12.369543+07		mqaqz3q1pnrpbjuwsj	A06
2550	de24bf6f	AGV01	go_charge	\N	completed	2026-06-12 16:51:49.835259+07	2026-06-12 16:53:12.467616+07	2026-06-12 16:54:30.581444+07	yield_siding	mqaqyure8mcir2tqtee	A06
3221	c7324d25	AGV02	go_to	16	completed	2026-06-16 16:26:50.237127+07	2026-06-16 16:26:50.237127+07	2026-06-16 16:27:35.74755+07	event:continue	mqgfu4bc6d4cjdmkuvc	A05
2561	003dace0	AGV01	go_charge	\N	cancelled	2026-06-12 16:55:02.118975+07	2026-06-12 17:01:09.091677+07	2026-06-12 17:01:23.107794+07	force-cancelled by user	mqaqyure8mcir2tqtee	yield_resume
2830	f933d275	AGV02	go_to	19	completed	2026-06-15 11:42:43.058002+07	2026-06-15 11:42:43.057994+07	2026-06-15 11:43:19.843898+07		mqeq8vzlt7bftsfe1h	A06
3432	0dfe4de0	AGV01	go_charge	\N	completed	2026-06-18 08:40:40.274419+07	2026-06-18 08:40:40.274419+07	2026-06-18 08:40:46.006654+07		mqiu2bxa69hz320r7ly	Sạc Pin
2832	970d7839	AGV02	go_to	17	completed	2026-06-15 11:42:43.079857+07	2026-06-15 11:44:00.134836+07	2026-06-15 11:44:16.109601+07		mqeq8vzlt7bftsfe1h	A06
2829	b80fb5bd	AGV01	go_to	17	completed	2026-06-15 11:42:37.345207+07	2026-06-15 11:43:08.14454+07	2026-06-15 11:44:17.46265+07	lifecycle:picking:confirmed	mqeq8rf9l5qzr1bowyq	A06
3219	d9689e35	AGV01	go_to	15	completed	2026-06-16 16:26:30.928982+07	2026-06-16 16:29:09.361241+07	2026-06-16 16:29:22.038884+07	event:continue	mqgftpa7owxsvi8mh7	A05
2835	d35ac2fe	AGV02	go_to	17	completed	2026-06-15 11:44:16.119592+07	2026-06-15 11:47:45.602731+07	2026-06-15 11:47:57.901266+07	lifecycle:picking:confirmed	mqeq8vzlt7bftsfe1h	A06
2841	8b4c862b	AGV02	go_charge	\N	cancelled	2026-06-15 11:47:57.921752+07	2026-06-15 11:48:12.351536+07	2026-06-15 11:49:04.366113+07	force-cancelled by user	mqeq8vzlt7bftsfe1h	A06
2840	6ee56f9c	AGV01	go_charge	\N	cancelled	2026-06-15 11:46:54.634052+07	2026-06-15 11:46:54.63404+07	2026-06-15 11:49:19.409246+07	force-cancelled by user	mqeqea43f8sc5vd82ji	Sạc Pin
2845	d8c46935	AGV02	go_charge	\N	completed	2026-06-15 11:51:21.314284+07	2026-06-15 11:51:21.314265+07	2026-06-15 11:51:35.568499+07		mqeqjzvgqrz2pvr6enh	Sạc Pin
3225	b480be54	AGV02	go_to	18	completed	2026-06-16 16:26:50.275667+07	2026-06-16 16:29:56.686116+07	2026-06-16 16:31:13.583682+07	lifecycle:picking:confirmed	mqgfu4bc6d4cjdmkuvc	A05
2918	e23f60c2	AGV02	go_charge	\N	completed	2026-06-16 09:03:49.890395+07	2026-06-16 09:04:04.259701+07	2026-06-16 09:04:54.474776+07	charge_arrived	mqfzx5tha60osk3utge	A06
2976	c467f800	AGV02	go_charge	\N	completed	2026-06-16 10:04:55.561191+07	2026-06-16 10:04:55.561174+07	2026-06-16 10:05:12.076917+07		mqg26z9gec8c83m7x48	Sạc Pin
3050	23a6e20c	AGV01	go_charge	14	completed	2026-06-16 11:26:58.036086+07	2026-06-16 11:26:58.037253+07	2026-06-16 11:27:11.090007+07	off_route	mqg4ip6rvwvjk57emj	A05
3054	88c5237d	AGV01	go_to	64	running	2026-06-16 11:27:28.28353+07	2026-06-16 11:27:28.284067+07	\N		mqg4ip6rvwvjk57emj	A05
3053	6dc1ee9d	AGV01	go_to	2	completed	2026-06-16 11:27:11.171986+07	2026-06-16 11:27:28.290643+07	2026-06-16 11:27:43.435819+07	off_route	mqg4ip6rvwvjk57emj	A05
3058	4a2861a8	AGV01	go_to	4	completed	2026-06-16 11:27:57.879222+07	2026-06-16 11:27:57.880729+07	2026-06-16 11:28:18.400658+07	off_route	mqg4ip6rvwvjk57emj	A05
3057	4f6d2dec	AGV01	go_to	2	cancelled	2026-06-16 11:27:43.456771+07	\N	2026-06-16 11:31:09.740015+07	cancelled by user	mqg4ip6rvwvjk57emj	A05
3104	6a97644b	AGV01	go_charge	\N	cancelled	2026-06-16 13:26:07.22724+07	\N	2026-06-16 13:26:20.395284+07	cancelled by user	mqg9dpsqq4qrrx9oib	A02
3109	dd0b7006	AGV01	go_to	19	completed	2026-06-16 13:26:54.883356+07	2026-06-16 13:26:54.883348+07	2026-06-16 13:26:54.889732+07	dest_wait	mqg9db1mma8mrrvp1aa	dest_retry
3105	26809a63	AGV02	go_to	19	cancelled	2026-06-16 13:26:47.51565+07	2026-06-16 13:26:47.515644+07	2026-06-16 13:58:33.247752+07	force-cancelled by user	mqg9ekwqmgwzmof7bed	A02
3106	b4e9d810	AGV02	go_to	16	cancelled	2026-06-16 13:26:47.534099+07	\N	2026-06-16 13:58:33.249856+07	cancelled by user	mqg9ekwqmgwzmof7bed	A02
3164	ed812af7	AGV01	go_charge	\N	queued	2026-06-16 14:32:55.374824+07	\N	\N	\N	mqgbrmgwpqnxrwntcjm	A02
3165	f83cdf58	AGV02	go_to	19	completed	2026-06-16 14:33:11.296162+07	2026-06-16 14:33:11.296162+07	2026-06-16 14:33:24.384743+07		mqgbryrczuw7o3qrha	A02
3433	b224ee37	AGV01	go_charge	\N	completed	2026-06-18 08:40:40.286587+07	2026-06-18 08:40:46.008763+07	2026-06-18 08:42:00.079544+07	charge_arrived	mqiu2bxa69hz320r7ly	Sạc Pin
3167	4d9c8c05	AGV02	go_to	16	completed	2026-06-16 14:33:11.323735+07	2026-06-16 14:34:15.202482+07	2026-06-16 14:35:00.752212+07	event:continue	mqgbryrczuw7o3qrha	A02
3220	84a47cff	AGV02	go_to	19	completed	2026-06-16 16:26:50.216051+07	2026-06-16 16:26:50.216051+07	2026-06-16 16:26:50.230811+07	dest_wait	mqgfu4bc6d4cjdmkuvc	A05
3230	830cb3e0	AGV02	go_charge	\N	completed	2026-06-16 16:31:13.597682+07	2026-06-16 16:31:28.219641+07	2026-06-16 16:32:11.789709+07	charge_arrived	mqgfu4bc6d4cjdmkuvc	A05
3303	40b5c4af	AGV01	go_charge	14	cancelled	2026-06-17 15:17:12.194484+07	2026-06-17 15:17:12.195486+07	2026-06-17 15:18:13.523454+07	force-cancelled by user	mqhsqv1erceejbo0cm	Sạc Pin
3343	1fa40d53	AGV01	go_to	15	cancelled	2026-06-17 15:43:37.090653+07	2026-06-17 15:45:05.342678+07	2026-06-17 15:50:47.680915+07	force-cancelled by user	mqhtqe24m1idh8dw9u	A05
3398	41110563	AGV02	go_to	18	completed	2026-06-17 16:42:03.323001+07	2026-06-17 16:42:03.323001+07	2026-06-17 16:42:13.445818+07	off_route	mqhvoyr9beumsloftrw	yield_resume
3405	47ec9b9d	AGV02	go_to	2	completed	2026-06-17 16:46:01.525875+07	2026-06-17 16:46:01.528398+07	2026-06-17 16:46:10.405819+07	off_route	mqhvoyr9beumsloftrw	A05
3404	a3e1d84e	AGV02	go_charge	\N	cancelled	2026-06-17 16:45:48.483823+07	\N	2026-06-17 16:54:29.943938+07	cancelled by user	mqhvoyr9beumsloftrw	A05
3414	a1b563dd	AGV01	go_charge	\N	cancelled	2026-06-18 08:12:38.402095+07	\N	2026-06-18 08:40:12.398777+07	cancelled by user	mqit2a1jo8v278sc1x	A05
3430	3bad1e36	AGV01	go_charge	13	cancelled	2026-06-18 08:40:28.288584+07	2026-06-18 08:40:28.290589+07	2026-06-18 08:40:34.178862+07	force-cancelled by user	mqiu1wsd2rfx45z8osp	Sạc Pin
3461	54f5cd24	AGV01	go_to	18	cancelled	2026-06-19 16:07:15.80833+07	\N	2026-06-19 16:07:29.218335+07	cancelled by user	\N	\N
3447	77a22b52	AGV02	go_to	19	completed	2026-06-18 08:54:12.214418+07	2026-06-18 08:54:31.584064+07	2026-06-18 08:54:50.470574+07		mqiuj988eyw7f3ggq4l	A02
3449	0109662f	AGV01	go_to	15	completed	2026-06-18 08:54:47.733577+07	2026-06-18 08:55:10.227996+07	2026-06-18 08:59:47.819193+07	lifecycle:picking:confirmed	mqiuh3by2ycpfx3pkt2	A02
3446	11f4d575	AGV02	go_charge	\N	completed	2026-06-18 08:53:50.030127+07	2026-06-18 09:01:15.083048+07	2026-06-18 09:01:52.214308+07	charge_arrived	mqiuj988eyw7f3ggq4l	A02
3455	87f51c94	AGV01	go_to	17	queued	2026-06-19 11:56:51.432444+07	\N	\N	\N	\N	\N
3467	a0af70d9	AGV01	go_to	15	cancelled	2026-06-19 16:09:35.179176+07	\N	2026-06-19 16:09:52.570247+07	cancelled by user	\N	\N
3462	a708aa2a	AGV01	go_to	18	cancelled	2026-06-19 16:09:35.041617+07	\N	2026-06-19 16:09:52.570247+07	cancelled by user	\N	\N
3465	f696a7e1	AGV01	go_to	17	cancelled	2026-06-19 16:09:35.135128+07	\N	2026-06-19 16:09:52.570247+07	cancelled by user	\N	\N
3469	564e6491	AGV01	go_to	18	completed	2026-06-22 11:18:10.516649+07	2026-06-22 11:20:25.719536+07	2026-06-22 11:20:39.904998+07		\N	\N
3473	0d3314e0	AGV01	go_charge	\N	completed	2026-06-22 11:30:31.307641+07	2026-06-22 11:30:31.307641+07	2026-06-22 11:30:45.83718+07		mqopw60bn1t0czb6i3k	Sạc Pin
3475	417c6e6a	AGV01	go_to	18	queued	2026-06-22 11:36:00.726759+07	\N	\N	\N	\N	\N
3483	20b1eb5d	AGV01	go_charge	\N	completed	2026-06-22 11:55:20.510881+07	2026-06-22 11:55:20.510881+07	2026-06-22 11:55:34.361664+07	off_route	mqoqs344gikx5dgo7s5	Sạc Pin
3478	3833a2bd	AGV01	go_charge	\N	completed	2026-06-22 11:39:27.094319+07	2026-06-22 11:39:41.032408+07	2026-06-22 11:40:27.257496+07	off_route	mqoq7n6javlrnc32a6o	Sạc Pin
3487	9c236c04	AGV01	go_to	18	completed	2026-06-23 13:50:55.887357+07	2026-06-23 13:53:55.467216+07	2026-06-23 13:54:13.59252+07	lifecycle:picking:confirmed	\N	\N
3484	3037989b	AGV01	go_charge	\N	cancelled	2026-06-22 11:55:20.539986+07	\N	2026-06-22 11:55:58.514646+07	cancelled by user	mqoqs344gikx5dgo7s5	Sạc Pin
3485	2f440e9b	AGV01	go_to	8	cancelled	2026-06-22 11:55:34.360659+07	2026-06-22 11:55:34.363656+07	2026-06-22 11:55:58.514646+07	force-cancelled by user	mqoqs344gikx5dgo7s5	Sạc Pin
2583	b530fe9a	AGV02	go_to	17	completed	2026-06-12 17:13:23.375166+07	2026-06-12 17:14:26.155529+07	2026-06-12 17:14:42.1386+07		mqarqkqx06pk2g82oo86	A06
2594	e9773bc7	AGV02	go_to	14	completed	2026-06-13 10:31:30.611058+07	2026-06-13 10:31:30.611043+07	2026-06-13 10:31:31.531785+07		mqbst2c0xrwp544dr4	yield_siding
2556	39a8ba6d	AGV02	go_to	19	completed	2026-06-12 16:52:13.778871+07	2026-06-12 16:52:32.873326+07	2026-06-12 16:52:52.61919+07	lifecycle:picking:confirmed	mqaqz3q1pnrpbjuwsj	dest_retry
2553	08a65cf3	AGV02	go_to	17	completed	2026-06-12 16:52:01.458713+07	2026-06-12 16:52:52.619245+07	2026-06-12 16:53:08.495596+07		mqaqz3q1pnrpbjuwsj	A06
2578	5b930f9b	AGV01	go_to	17	completed	2026-06-12 17:13:14.28353+07	2026-06-12 17:13:48.10963+07	2026-06-12 17:14:50.584906+07	lifecycle:picking:confirmed	mqarqdtestjxz44yjte	A06
2549	49211b3b	AGV01	go_to	17	completed	2026-06-12 16:51:49.833766+07	2026-06-12 16:52:22.837483+07	2026-06-12 16:53:12.467504+07	lifecycle:picking:confirmed	mqaqyure8mcir2tqtee	A06
2557	2b3b4ae2	AGV02	go_to	17	completed	2026-06-12 16:52:52.629613+07	2026-06-12 16:53:08.496013+07	2026-06-12 16:53:28.885517+07		mqaqz3q1pnrpbjuwsj	A06
2598	5726c79b	AGV02	go_charge	\N	completed	2026-06-13 10:33:40.693764+07	2026-06-13 10:33:55.001774+07	2026-06-13 10:34:36.506067+07	charge_arrived	mqbst2c0xrwp544dr4	A06
2558	a72ad8a8	AGV02	go_to	17	completed	2026-06-12 16:53:08.50802+07	2026-06-12 16:53:28.886703+07	2026-06-12 16:53:49.310032+07	lifecycle:picking:confirmed	mqaqz3q1pnrpbjuwsj	A06
2560	297a7419	AGV01	go_to	16	completed	2026-06-12 16:54:30.582208+07	2026-06-12 16:54:30.5822+07	2026-06-12 17:01:09.091578+07	lifecycle:picking:confirmed	mqaqyure8mcir2tqtee	yield_siding
2562	7b879dd8	AGV01	go_charge	\N	cancelled	2026-06-12 17:01:27.98689+07	2026-06-12 17:01:27.986885+07	2026-06-12 17:01:56.223035+07	force-cancelled by user	mqarb8vtlvyxfbbu7tr	Sạc Pin
2563	43298aee	AGV01	go_charge	\N	cancelled	2026-06-12 17:01:28.002567+07	\N	2026-06-12 17:01:56.223443+07	cancelled by user	mqarb8vtlvyxfbbu7tr	Sạc Pin
2566	07f09762	AGV01	go_charge	\N	queued	2026-06-12 17:05:57.160722+07	\N	\N	\N	mqarh0k1ffiduypms3m	A06
2565	b3d8a93c	AGV01	go_to	17	running	2026-06-12 17:05:57.15877+07	2026-06-12 17:06:29.149284+07	\N		mqarh0k1ffiduypms3m	A06
2564	c216ed55	AGV01	go_to	19	completed	2026-06-12 17:05:57.129426+07	2026-06-12 17:05:57.129415+07	2026-06-12 17:06:29.14914+07	lifecycle:picking:confirmed	mqarh0k1ffiduypms3m	A06
2584	8f824325	AGV02	go_to	17	completed	2026-06-12 17:14:26.166659+07	2026-06-12 17:14:42.13897+07	2026-06-12 17:15:00.064581+07		mqarqkqx06pk2g82oo86	A06
2567	6fed454b	AGV02	go_to	19	completed	2026-06-12 17:06:23.208052+07	2026-06-12 17:06:23.208047+07	2026-06-12 17:06:43.47227+07		mqarhko9w52e51ltexi	A06
2568	45204160	AGV02	go_to	19	cancelled	2026-06-12 17:06:23.216088+07	2026-06-12 17:06:43.473371+07	2026-06-12 17:07:37.108708+07	force-cancelled by user	mqarhko9w52e51ltexi	A06
2570	3aaff993	AGV02	go_to	17	cancelled	2026-06-12 17:06:23.467735+07	\N	2026-06-12 17:07:37.109084+07	cancelled by user	mqarhko9w52e51ltexi	A06
2569	0b324497	AGV02	go_charge	\N	cancelled	2026-06-12 17:06:23.468741+07	\N	2026-06-12 17:07:37.109084+07	cancelled by user	mqarhko9w52e51ltexi	A06
2571	1688df4a	AGV02	go_to	19	cancelled	2026-06-12 17:08:15.914008+07	2026-06-12 17:08:15.914+07	2026-06-12 17:09:03.645507+07	force-cancelled by user	mqarjzn0t72d3ussjh	A06
2572	8832fe94	AGV02	go_to	17	cancelled	2026-06-12 17:08:15.934714+07	\N	2026-06-12 17:09:03.645744+07	cancelled by user	mqarjzn0t72d3ussjh	A06
2573	a237c52d	AGV02	go_charge	\N	cancelled	2026-06-12 17:08:15.936534+07	\N	2026-06-12 17:09:03.645744+07	cancelled by user	mqarjzn0t72d3ussjh	A06
2574	137fa49d	AGV01	go_charge	\N	cancelled	2026-06-12 17:11:12.345523+07	2026-06-12 17:11:12.345507+07	2026-06-12 17:11:20.298828+07	force-cancelled by user	mqarnrrtwr4tmzs2uk	Sạc Pin
2595	a98c3618	AGV02	go_to	14	completed	2026-06-13 10:31:30.631211+07	2026-06-13 10:31:31.533964+07	2026-06-13 10:31:46.177283+07	charge_arrived	mqbst2c0xrwp544dr4	yield_siding
2575	ba96503f	AGV01	go_charge	\N	completed	2026-06-12 17:11:25.700543+07	2026-06-12 17:11:25.700531+07	2026-06-12 17:11:39.99598+07		mqaro22xalk461xoaoi	Sạc Pin
2576	d81a04b2	AGV01	go_charge	\N	completed	2026-06-12 17:11:25.710593+07	2026-06-12 17:11:39.996346+07	2026-06-12 17:12:35.72548+07	charge_arrived	mqaro22xalk461xoaoi	Sạc Pin
2577	da5401b2	AGV01	go_to	19	completed	2026-06-12 17:13:14.248318+07	2026-06-12 17:13:14.24831+07	2026-06-12 17:13:48.109547+07	lifecycle:picking:confirmed	mqarqdtestjxz44yjte	A06
2599	478ea0e1	AGV01	go_to	19	completed	2026-06-13 10:35:20.936445+07	2026-06-13 10:35:20.936431+07	2026-06-13 10:35:57.238558+07	lifecycle:picking:confirmed	mqbsyjqa3lzl8d5gxbe	A06
2585	dd65029e	AGV02	go_to	17	completed	2026-06-12 17:14:42.146956+07	2026-06-12 17:15:00.064778+07	2026-06-12 17:15:20.467561+07	lifecycle:picking:confirmed	mqarqkqx06pk2g82oo86	A06
2580	69a20684	AGV02	go_to	19	completed	2026-06-12 17:13:23.217045+07	2026-06-12 17:13:23.217027+07	2026-06-12 17:14:01.184883+07		mqarqkqx06pk2g82oo86	A06
2581	5e36efe3	AGV02	go_to	19	completed	2026-06-12 17:13:23.224514+07	2026-06-12 17:14:01.185735+07	2026-06-12 17:14:26.155454+07	lifecycle:picking:confirmed	mqarqkqx06pk2g82oo86	A06
2588	c726ab08	AGV01	go_to	17	completed	2026-06-13 10:30:47.499902+07	2026-06-13 10:31:23.947833+07	2026-06-13 10:31:47.66681+07	lifecycle:picking:confirmed	mqbssomh4g6lebikc0z	A06
2582	f9e2e875	AGV02	go_charge	\N	completed	2026-06-12 17:13:23.377176+07	2026-06-12 17:15:20.467708+07	2026-06-12 17:15:34.921254+07		mqarqkqx06pk2g82oo86	A06
2607	5e57a1d6	AGV02	go_to	10	completed	2026-06-13 10:36:04.031342+07	2026-06-13 10:36:04.031332+07	2026-06-13 10:45:07.878209+07	lifecycle:picking:confirmed	mqbsyywk2sajqc7j6h5	yield_siding
2586	a224f22a	AGV02	go_charge	\N	completed	2026-06-12 17:15:20.487579+07	2026-06-12 17:15:34.922169+07	2026-06-12 17:16:00.432315+07	event:continue	mqarqkqx06pk2g82oo86	A06
2579	c71729e5	AGV01	go_charge	\N	cancelled	2026-06-12 17:13:14.28559+07	2026-06-12 17:14:50.585079+07	2026-06-12 17:16:28.818246+07	force-cancelled by user	mqarqdtestjxz44yjte	A06
2587	c546d3d4	AGV01	go_to	19	completed	2026-06-13 10:30:47.403402+07	2026-06-13 10:30:47.40338+07	2026-06-13 10:31:23.947323+07	lifecycle:picking:confirmed	mqbssomh4g6lebikc0z	A06
2596	ca4d86b8	AGV02	go_to	19	completed	2026-06-13 10:31:30.633892+07	2026-06-13 10:34:36.509171+07	2026-06-13 10:34:36.515908+07	already_at_dest	mqbst2c0xrwp544dr4	yield_resume
2592	fe81fd79	AGV02	go_to	17	completed	2026-06-13 10:31:05.149221+07	2026-06-13 10:31:46.178382+07	2026-06-13 10:32:28.104908+07		mqbst2c0xrwp544dr4	A06
2590	82743030	AGV02	go_to	19	completed	2026-06-13 10:31:05.11304+07	2026-06-13 10:31:05.11303+07	2026-06-13 10:31:29.58755+07		mqbst2c0xrwp544dr4	A06
2591	6543b1c5	AGV02	go_to	19	completed	2026-06-13 10:31:05.125684+07	2026-06-13 10:31:29.588621+07	2026-06-13 10:31:30.608999+07	yield_siding	mqbst2c0xrwp544dr4	A06
2589	ca16eb42	AGV01	go_charge	\N	completed	2026-06-13 10:30:47.503441+07	2026-06-13 10:31:47.667029+07	2026-06-13 10:34:47.973177+07	charge_arrived	mqbssomh4g6lebikc0z	A06
2597	4a2b7411	AGV02	go_to	17	completed	2026-06-13 10:31:46.209772+07	2026-06-13 10:32:28.105608+07	2026-06-13 10:33:40.654193+07	lifecycle:picking:confirmed	mqbst2c0xrwp544dr4	A06
2593	73cc4f50	AGV02	go_charge	\N	completed	2026-06-13 10:31:05.150675+07	2026-06-13 10:33:40.654701+07	2026-06-13 10:33:55.000048+07		mqbst2c0xrwp544dr4	A06
2603	dcfdf88b	AGV02	go_to	17	completed	2026-06-13 10:35:40.63167+07	2026-06-13 10:35:40.631656+07	2026-06-13 10:36:04.030828+07	yield_siding	mqbsyywk2sajqc7j6h5	A06
2602	29898293	AGV02	go_to	19	completed	2026-06-13 10:35:40.610764+07	2026-06-13 10:35:40.61075+07	2026-06-13 10:35:40.625688+07	dest_wait	mqbsyywk2sajqc7j6h5	A06
2600	e967980c	AGV01	go_to	17	completed	2026-06-13 10:35:20.97778+07	2026-06-13 10:35:57.238886+07	2026-06-13 10:37:07.331432+07	lifecycle:picking:confirmed	mqbsyjqa3lzl8d5gxbe	A06
2601	9ad95660	AGV01	go_charge	\N	completed	2026-06-13 10:35:20.980994+07	2026-06-13 10:37:07.332471+07	2026-06-13 10:37:52.169151+07	charge_arrived	mqbsyjqa3lzl8d5gxbe	A06
2609	ea7b7b10	AGV02	go_to	17	completed	2026-06-13 10:45:08.317046+07	2026-06-13 10:45:26.150865+07	2026-06-13 10:46:03.334955+07	lifecycle:picking:confirmed	mqbsyywk2sajqc7j6h5	A06
2605	47d8bcbe	AGV02	go_charge	\N	completed	2026-06-13 10:35:40.673407+07	2026-06-13 10:46:03.336441+07	2026-06-13 10:46:47.023006+07	charge_arrived	mqbsyywk2sajqc7j6h5	A06
2604	94d81557	AGV02	go_to	17	completed	2026-06-13 10:35:40.668654+07	2026-06-13 10:45:07.878448+07	2026-06-13 10:45:26.149721+07		mqbsyywk2sajqc7j6h5	A06
2606	89ab882a	AGV02	go_to	19	completed	2026-06-13 10:35:41.92963+07	2026-06-13 10:46:47.02435+07	2026-06-13 10:46:47.027541+07	pickup_already_done	mqbsyywk2sajqc7j6h5	dest_retry
2610	d4915a74	AGV02	go_charge	\N	completed	2026-06-13 10:49:05.701091+07	2026-06-13 10:49:05.70107+07	2026-06-13 10:49:20.114204+07		mqbtg84dv177f7iyox8	Sạc Pin
2608	6f924b1b	AGV02	go_to	17	completed	2026-06-13 10:36:14.167383+07	2026-06-13 10:46:47.02845+07	2026-06-13 10:47:37.440875+07	lifecycle:picking:confirmed	mqbsyywk2sajqc7j6h5	yield_resume
2836	ec4b8fc3	AGV01	go_charge	\N	cancelled	2026-06-15 11:44:17.484584+07	2026-06-15 11:44:50.628949+07	2026-06-15 11:46:47.343106+07	force-cancelled by user	mqeq8rf9l5qzr1bowyq	A06
2611	3da46933	AGV02	go_charge	\N	completed	2026-06-13 10:49:05.747458+07	2026-06-13 10:49:20.115574+07	2026-06-13 10:50:12.646218+07	charge_arrived	mqbtg84dv177f7iyox8	Sạc Pin
2612	828d0809	AGV01	go_to	19	completed	2026-06-13 10:55:46.519116+07	2026-06-13 10:55:46.519097+07	2026-06-13 10:56:19.445333+07	lifecycle:picking:confirmed	mqbtotdkfeae91xt438	A06
2633	e8c99470	AGV02	go_to	17	completed	2026-06-13 11:10:20.931349+07	2026-06-13 11:10:36.665787+07	2026-06-13 11:12:17.529578+07	lifecycle:picking:confirmed	mqbu67vbaij7qb0un3	A06
2645	648cb91b	AGV02	go_charge	\N	completed	2026-06-13 11:20:21.891231+07	2026-06-13 11:20:32.997444+07	2026-06-13 11:21:05.059434+07	charge_arrived	mqbukfst1rhuozqc6qn	Sạc Pin
2615	49e26894	AGV02	go_to	19	completed	2026-06-13 10:55:58.453312+07	2026-06-13 10:55:58.453296+07	2026-06-13 10:56:29.003349+07		mqbtp2ljx3yg0uf5w69	A06
2616	5d2fcad8	AGV02	go_to	19	completed	2026-06-13 10:55:58.467233+07	2026-06-13 10:56:29.004124+07	2026-06-13 10:56:31.645127+07	yield_siding	mqbtp2ljx3yg0uf5w69	A06
2619	561dc8b1	AGV02	go_to	14	completed	2026-06-13 10:56:31.646828+07	2026-06-13 10:56:31.646811+07	2026-06-13 10:56:32.772167+07		mqbtp2ljx3yg0uf5w69	yield_siding
2614	11ae678a	AGV01	go_to	17	completed	2026-06-13 10:55:46.842573+07	2026-06-13 10:56:19.446076+07	2026-06-13 10:56:53.174817+07	lifecycle:picking:confirmed	mqbtotdkfeae91xt438	A06
2632	3a95f11b	AGV02	go_charge	\N	completed	2026-06-13 11:09:18.467624+07	2026-06-13 11:12:17.529956+07	2026-06-13 11:12:31.955923+07		mqbu67vbaij7qb0un3	A06
2613	bb2f4d59	AGV01	go_charge	\N	completed	2026-06-13 10:55:46.846351+07	2026-06-13 10:56:53.175012+07	2026-06-13 10:57:08.206088+07		mqbtotdkfeae91xt438	A06
2646	ffb53dcc	AGV01	go_charge	\N	cancelled	2026-06-13 11:20:35.221501+07	2026-06-13 11:20:35.221459+07	2026-06-13 11:21:53.243129+07	force-cancelled by user	mqbukq3dm37izbbjulr	Sạc Pin
2620	d06074b3	AGV02	go_to	14	completed	2026-06-13 10:56:31.683168+07	2026-06-13 10:56:32.77357+07	2026-06-13 10:57:33.836649+07	off_route	mqbtp2ljx3yg0uf5w69	yield_siding
2628	6224cf4f	AGV01	go_charge	\N	cancelled	2026-06-13 11:09:09.269286+07	2026-06-13 11:10:29.852319+07	2026-06-13 11:12:46.193399+07	force-cancelled by user	mqbu60oe532p2qajqd4	A06
2623	a14daf7e	AGV02	go_charge	14	completed	2026-06-13 10:57:33.834394+07	2026-06-13 10:57:33.841654+07	2026-06-13 10:58:01.654217+07		mqbtp2ljx3yg0uf5w69	yield_siding
2622	f5b2ed15	AGV01	go_charge	\N	completed	2026-06-13 10:56:53.217727+07	2026-06-13 10:57:08.207545+07	2026-06-13 10:58:05.443338+07	charge_arrived	mqbtotdkfeae91xt438	A06
2624	67665bab	AGV02	go_charge	\N	completed	2026-06-13 10:57:34.114293+07	2026-06-13 10:58:01.654594+07	2026-06-13 10:58:26.744851+07	charge_arrived	mqbtp2ljx3yg0uf5w69	yield_siding
2634	1d8a4d63	AGV02	go_charge	\N	completed	2026-06-13 11:12:17.555125+07	2026-06-13 11:12:31.956224+07	2026-06-13 11:13:23.165838+07	charge_arrived	mqbu67vbaij7qb0un3	A06
2617	a6264e2a	AGV02	go_to	17	completed	2026-06-13 10:55:58.497541+07	2026-06-13 10:58:26.745649+07	2026-06-13 10:59:29.217105+07	lifecycle:picking:confirmed	mqbtp2ljx3yg0uf5w69	A06
2635	95b6a295	AGV01	go_charge	\N	completed	2026-06-13 11:12:54.201232+07	2026-06-13 11:12:54.201222+07	2026-06-13 11:14:44.51823+07	charge_arrived	mqbuauda707plh9ux8k	Sạc Pin
2618	24bfdfc0	AGV02	go_charge	\N	completed	2026-06-13 10:55:58.500574+07	2026-06-13 10:59:29.217599+07	2026-06-13 10:59:43.757072+07		mqbtp2ljx3yg0uf5w69	A06
2625	adf05c55	AGV02	go_charge	\N	completed	2026-06-13 10:59:29.250729+07	2026-06-13 10:59:43.757994+07	2026-06-13 11:00:30.354847+07	charge_arrived	mqbtp2ljx3yg0uf5w69	A06
2621	f2920594	AGV02	go_to	19	completed	2026-06-13 10:56:31.685903+07	2026-06-13 11:00:30.356338+07	2026-06-13 11:00:30.359733+07	pickup_already_done	mqbtp2ljx3yg0uf5w69	yield_resume
2626	1dfd9280	AGV01	go_to	19	completed	2026-06-13 11:09:09.125006+07	2026-06-13 11:09:09.125+07	2026-06-13 11:09:41.133259+07	lifecycle:picking:confirmed	mqbu60oe532p2qajqd4	A06
2629	b6a19fd6	AGV02	go_to	19	completed	2026-06-13 11:09:18.418526+07	2026-06-13 11:09:18.41851+07	2026-06-13 11:09:50.220111+07		mqbu67vbaij7qb0un3	A06
2630	74203235	AGV02	go_to	19	completed	2026-06-13 11:09:18.43164+07	2026-06-13 11:09:50.22052+07	2026-06-13 11:10:20.917716+07	lifecycle:picking:confirmed	mqbu67vbaij7qb0un3	A06
2627	6d8a6da9	AGV01	go_to	17	completed	2026-06-13 11:09:09.268258+07	2026-06-13 11:09:41.133328+07	2026-06-13 11:10:29.852154+07	lifecycle:picking:confirmed	mqbu60oe532p2qajqd4	A06
2631	0bbd1eef	AGV02	go_to	17	completed	2026-06-13 11:09:18.466766+07	2026-06-13 11:10:20.917879+07	2026-06-13 11:10:36.664874+07		mqbu67vbaij7qb0un3	A06
2647	94792669	AGV01	go_charge	\N	completed	2026-06-13 11:22:02.509135+07	2026-06-13 11:22:02.509123+07	2026-06-13 11:22:17.41739+07		mqbumlg00uo0xkiq0d4	Sạc Pin
2636	6db3e262	AGV01	go_to	19	completed	2026-06-13 11:14:59.263877+07	2026-06-13 11:14:59.26386+07	2026-06-13 11:15:31.835228+07	lifecycle:picking:confirmed	mqbudiv6rg7yytw6y6	A06
2653	295910f1	AGV02	go_to	19	completed	2026-06-13 11:44:39.676068+07	2026-06-13 11:44:51.625478+07	2026-06-13 11:45:10.900942+07		mqbvfomr66629qddiik	A06
2639	508dcd26	AGV02	go_to	19	completed	2026-06-13 11:15:15.355565+07	2026-06-13 11:15:15.355553+07	2026-06-13 11:15:41.403723+07		mqbudvageqado1sxj7s	A06
2648	ef2cb44c	AGV01	go_charge	\N	completed	2026-06-13 11:22:02.531065+07	2026-06-13 11:22:17.41769+07	2026-06-13 11:23:12.086062+07	charge_arrived	mqbumlg00uo0xkiq0d4	Sạc Pin
2637	97ea48eb	AGV01	go_to	17	completed	2026-06-13 11:14:59.29538+07	2026-06-13 11:15:31.83535+07	2026-06-13 11:15:58.282409+07	lifecycle:picking:confirmed	mqbudiv6rg7yytw6y6	A06
2638	1744062f	AGV01	go_charge	\N	completed	2026-06-13 11:14:59.298038+07	2026-06-13 11:15:58.282516+07	2026-06-13 11:16:13.266728+07		mqbudiv6rg7yytw6y6	A06
2640	1f3346f5	AGV02	go_to	19	completed	2026-06-13 11:15:15.360214+07	2026-06-13 11:15:41.404599+07	2026-06-13 11:16:19.297584+07	lifecycle:picking:confirmed	mqbudvageqado1sxj7s	A06
2642	b1214359	AGV02	go_charge	\N	cancelled	2026-06-13 11:15:15.38539+07	\N	2026-06-13 11:20:15.382627+07	cancelled by user	mqbudvageqado1sxj7s	A06
2641	c82807e4	AGV02	go_to	17	cancelled	2026-06-13 11:15:15.384302+07	2026-06-13 11:16:19.297983+07	2026-06-13 11:20:15.382172+07	force-cancelled by user	mqbudvageqado1sxj7s	A06
2643	eb20c8af	AGV01	go_charge	\N	cancelled	2026-06-13 11:15:58.33853+07	2026-06-13 11:16:13.267304+07	2026-06-13 11:20:28.064398+07	force-cancelled by user	mqbudiv6rg7yytw6y6	A06
2644	2e8f3202	AGV02	go_charge	\N	completed	2026-06-13 11:20:21.877947+07	2026-06-13 11:20:21.877941+07	2026-06-13 11:20:32.994132+07		mqbukfst1rhuozqc6qn	Sạc Pin
2659	7c56947b	AGV01	go_charge	\N	completed	2026-06-13 11:47:02.61877+07	2026-06-13 11:47:02.618755+07	2026-06-13 11:48:16.420132+07	charge_arrived	mqbvfelsx3mlcgxzhbh	yield_resume
2652	a1354f23	AGV02	go_to	19	completed	2026-06-13 11:44:39.668644+07	2026-06-13 11:44:39.668639+07	2026-06-13 11:44:51.625229+07		mqbvfomr66629qddiik	A06
2658	88b015f4	AGV01	go_to	8	completed	2026-06-13 11:46:02.086769+07	2026-06-13 11:46:02.086765+07	2026-06-13 11:46:39.239914+07	parked_siding	mqbvfelsx3mlcgxzhbh	yield_siding
2649	e2c82f52	AGV01	go_to	19	completed	2026-06-13 11:44:26.690307+07	2026-06-13 11:44:26.6903+07	2026-06-13 11:44:59.675512+07	lifecycle:picking:confirmed	mqbvfelsx3mlcgxzhbh	A06
2656	20d460bd	AGV02	go_to	19	completed	2026-06-13 11:44:51.740122+07	2026-06-13 11:45:10.901489+07	2026-06-13 11:46:45.655655+07	lifecycle:picking:confirmed	mqbvfomr66629qddiik	A06
2651	46cb73f6	AGV01	go_to	17	completed	2026-06-13 11:44:26.961328+07	2026-06-13 11:44:59.675598+07	2026-06-13 11:45:43.438501+07	lifecycle:picking:confirmed	mqbvfelsx3mlcgxzhbh	A06
2655	add99278	AGV02	go_charge	\N	completed	2026-06-13 11:44:39.697393+07	2026-06-13 11:47:29.722979+07	2026-06-13 11:47:44.008675+07		mqbvfomr66629qddiik	A06
2650	0a50ffba	AGV01	go_charge	\N	completed	2026-06-13 11:44:26.963262+07	2026-06-13 11:45:43.438793+07	2026-06-13 11:45:58.39762+07		mqbvfelsx3mlcgxzhbh	A06
2657	c8e02a53	AGV01	go_charge	\N	completed	2026-06-13 11:45:43.466118+07	2026-06-13 11:45:58.3984+07	2026-06-13 11:46:02.086103+07	yield_siding	mqbvfelsx3mlcgxzhbh	A06
2654	c825d10e	AGV02	go_to	17	completed	2026-06-13 11:44:39.695535+07	2026-06-13 11:46:45.655716+07	2026-06-13 11:47:29.722907+07	lifecycle:picking:confirmed	mqbvfomr66629qddiik	A06
2661	2a137db9	AGV01	go_to	19	completed	2026-06-13 11:50:58.333279+07	2026-06-13 11:50:58.333274+07	2026-06-13 11:51:38.947168+07	lifecycle:picking:confirmed	mqbvnssz02xghpex3xpy	A06
2660	c625da87	AGV02	go_charge	\N	cancelled	2026-06-13 11:47:29.737181+07	2026-06-13 11:47:44.008906+07	2026-06-13 11:49:11.269955+07	force-cancelled by user	mqbvfomr66629qddiik	A06
2838	117bb0dc	AGV02	go_to	18	completed	2026-06-15 11:46:19.247381+07	2026-06-15 11:46:19.24928+07	2026-06-15 11:46:37.050245+07		mqeq8vzlt7bftsfe1h	A06
2664	aaf3bc38	AGV02	go_to	19	completed	2026-06-13 11:51:09.63431+07	2026-06-13 11:51:09.634296+07	2026-06-13 11:51:43.189308+07		mqbvo1j2sp4iob7ybwd	A06
2665	70ff9a2b	AGV02	go_to	19	completed	2026-06-13 11:51:09.643872+07	2026-06-13 11:51:43.18976+07	2026-06-13 11:52:17.950053+07	lifecycle:picking:confirmed	mqbvo1j2sp4iob7ybwd	A06
2663	228a7eda	AGV01	go_to	17	completed	2026-06-13 11:50:58.54624+07	2026-06-13 11:51:38.947453+07	2026-06-13 11:53:06.290973+07	lifecycle:picking:confirmed	mqbvnssz02xghpex3xpy	A06
2669	f3e6fedc	AGV02	go_to	17	completed	2026-06-13 11:52:33.841867+07	2026-06-13 11:52:53.129604+07	2026-06-13 11:52:53.134665+07	dest_wait	mqbvo1j2sp4iob7ybwd	A06
2666	86efb040	AGV02	go_to	17	completed	2026-06-13 11:51:09.664425+07	2026-06-13 11:52:17.950356+07	2026-06-13 11:52:33.835035+07		mqbvo1j2sp4iob7ybwd	A06
2668	ce844c52	AGV02	go_to	17	completed	2026-06-13 11:52:17.9656+07	2026-06-13 11:52:33.836026+07	2026-06-13 11:52:53.128922+07		mqbvo1j2sp4iob7ybwd	A06
2662	595c0165	AGV01	go_charge	\N	completed	2026-06-13 11:50:58.547281+07	2026-06-13 11:53:06.291097+07	2026-06-13 11:57:49.918261+07	charge_arrived	mqbvnssz02xghpex3xpy	A06
2839	311b20f0	AGV02	go_to	18	completed	2026-06-15 11:46:19.303351+07	2026-06-15 11:46:37.052097+07	2026-06-15 11:47:45.602647+07	lifecycle:picking:confirmed	mqeq8vzlt7bftsfe1h	A06
2667	4c4617e8	AGV02	go_charge	\N	completed	2026-06-13 11:51:09.666138+07	2026-06-13 11:57:54.027887+07	2026-06-13 11:58:08.448394+07		mqbvo1j2sp4iob7ybwd	A06
2843	7df5ee66	AGV01	go_charge	\N	cancelled	2026-06-15 11:49:39.124338+07	2026-06-15 11:49:39.124334+07	2026-06-15 11:49:59.631554+07	force-cancelled by user	mqeqht1f39nw76h727l	Sạc Pin
2844	39add3c0	AGV01	go_charge	\N	cancelled	2026-06-15 11:49:39.14285+07	\N	2026-06-15 11:49:59.632057+07	cancelled by user	mqeqht1f39nw76h727l	Sạc Pin
2842	d01b0611	AGV02	go_charge	\N	cancelled	2026-06-15 11:49:26.671535+07	2026-06-15 11:49:26.671526+07	2026-06-15 11:50:40.810726+07	force-cancelled by user	mqeqhjfedvudjja9dka	Sạc Pin
2846	e5c07d14	AGV02	go_charge	\N	completed	2026-06-15 11:51:21.326016+07	2026-06-15 11:51:35.569084+07	2026-06-15 11:53:05.138373+07	charge_arrived	mqeqjzvgqrz2pvr6enh	Sạc Pin
2919	bb78a05e	AGV01	go_to	19	completed	2026-06-16 09:09:12.628255+07	2026-06-16 09:09:12.628239+07	2026-06-16 09:09:46.43401+07	lifecycle:picking:confirmed	mqg07bufsnhojl0b6d	A06
3322	7a2ab955	AGV01	go_to	15	completed	2026-06-17 15:25:52.7411+07	2026-06-17 15:26:16.283487+07	2026-06-17 15:26:34.044342+07		mqht10otruzwoswgsvq	A05
2920	695e4964	AGV01	go_charge	\N	completed	2026-06-16 09:09:12.796611+07	2026-06-16 09:10:29.185499+07	2026-06-16 09:10:43.921071+07		mqg07bufsnhojl0b6d	A06
2923	d5737e98	AGV02	go_to	19	cancelled	2026-06-16 09:09:21.22165+07	2026-06-16 09:09:54.223843+07	2026-06-16 09:12:05.103457+07	force-cancelled by user	mqg07igt9gwenij5fm9	A06
2925	3fdb84ac	AGV02	go_charge	\N	cancelled	2026-06-16 09:09:21.239402+07	\N	2026-06-16 09:12:05.10361+07	cancelled by user	mqg07igt9gwenij5fm9	A06
2928	be494285	AGV02	go_charge	\N	cancelled	2026-06-16 09:12:41.038417+07	2026-06-16 09:12:41.038413+07	2026-06-16 09:14:01.404406+07	force-cancelled by user	mqg0bsnya7woo0s2yfj	Sạc Pin
2978	dd3b8d31	AGV01	go_charge	\N	cancelled	2026-06-16 10:05:06.800398+07	2026-06-16 10:05:06.800383+07	2026-06-16 10:05:50.564815+07	force-cancelled by user	mqg277y4k9sma3m7eve	Sạc Pin
2977	be3876e1	AGV02	go_charge	\N	completed	2026-06-16 10:04:55.580306+07	2026-06-16 10:05:12.078325+07	2026-06-16 10:05:53.66968+07	charge_arrived	mqg26z9gec8c83m7x48	Sạc Pin
3052	502d879b	AGV01	go_to	2	completed	2026-06-16 11:27:11.089131+07	2026-06-16 11:27:11.090391+07	2026-06-16 11:27:28.283872+07	off_route	mqg4ip6rvwvjk57emj	A05
3051	f2309134	AGV01	go_charge	\N	cancelled	2026-06-16 11:26:58.154107+07	\N	2026-06-16 11:31:09.740015+07	cancelled by user	mqg4ip6rvwvjk57emj	A05
3110	b5695a36	AGV01	go_to	19	completed	2026-06-16 13:58:46.16818+07	2026-06-16 13:58:46.168119+07	2026-06-16 13:59:10.788272+07	lifecycle:picking:confirmed	mqg9db1mma8mrrvp1aa	dest_retry
3175	c74fad7e	AGV02	go_to	16	queued	2026-06-16 14:35:34.614624+07	\N	\N	\N	mqgbryrczuw7o3qrha	A02
3241	b89a1734	AGV02	go_to	17	queued	2026-06-16 16:40:56.707762+07	\N	\N	\N	mqggc9el0vuse3cpqro	A05
3232	3f844dfb	AGV01	go_to	18	completed	2026-06-16 16:40:38.159294+07	2026-06-16 16:41:17.722733+07	2026-06-16 16:44:41.526158+07	lifecycle:picking:confirmed	mqggbuwu3cpos7vdpfs	A05
3328	dd64ec1d	AGV02	go_charge	\N	cancelled	2026-06-17 15:30:08.447197+07	\N	2026-06-17 15:36:50.406936+07	cancelled by user	mqht1i431tvwdr671ixh	A05
3239	b755fdb7	AGV02	go_to	16	completed	2026-06-16 16:40:56.69957+07	2026-06-16 16:44:44.506154+07	2026-06-16 16:45:00.796171+07		mqggc9el0vuse3cpqro	A05
3327	0eed0063	AGV01	go_charge	\N	cancelled	2026-06-17 15:29:38.458278+07	2026-06-17 15:29:53.708507+07	2026-06-17 15:36:54.910125+07	force-cancelled by user	mqht10otruzwoswgsvq	A05
3246	3eeea69f	AGV02	go_to	16	completed	2026-06-16 16:45:00.806688+07	2026-06-16 16:45:15.044979+07	2026-06-16 16:45:29.037779+07		mqggc9el0vuse3cpqro	A05
3247	fd429dcf	AGV02	go_to	16	completed	2026-06-16 16:45:15.057952+07	2026-06-16 16:45:29.043878+07	2026-06-16 16:46:14.446296+07	lifecycle:picking:confirmed	mqggc9el0vuse3cpqro	A05
3234	e86da485	AGV01	go_charge	\N	running	2026-06-16 16:40:38.181292+07	2026-06-16 16:46:42.84348+07	\N		mqggbuwu3cpos7vdpfs	A05
3305	b10e0400	AGV01	go_to	19	completed	2026-06-17 15:23:53.342597+07	2026-06-17 15:23:53.342597+07	2026-06-17 15:24:28.402298+07	lifecycle:picking:confirmed	mqht10otruzwoswgsvq	A05
3306	858c6e67	AGV01	go_to	15	completed	2026-06-17 15:23:53.50596+07	2026-06-17 15:25:14.528953+07	2026-06-17 15:25:30.153942+07		mqht10otruzwoswgsvq	A05
3330	b48f3489	AGV01	go_charge	\N	completed	2026-06-17 15:37:10.081041+07	2026-06-17 15:38:30.905595+07	2026-06-17 15:39:09.63259+07	charge_arrived	mqhti3hmhclorilf5sd	Sạc Pin
3466	fc7c07e5	AGV01	go_to	16	cancelled	2026-06-19 16:09:35.155644+07	\N	2026-06-19 16:09:52.570247+07	cancelled by user	\N	\N
3348	e3c00b6d	AGV02	go_to	19	completed	2026-06-17 15:44:01.353582+07	2026-06-17 15:44:27.277664+07	2026-06-17 15:45:01.391972+07	lifecycle:picking:confirmed	mqhtqwszecj5hpyoiqr	A05
3345	4e411c35	AGV01	go_to	16	cancelled	2026-06-17 15:43:37.092662+07	\N	2026-06-17 15:50:47.680915+07	cancelled by user	mqhtqe24m1idh8dw9u	A05
3350	f4007032	AGV02	go_to	17	cancelled	2026-06-17 15:44:01.383407+07	\N	2026-06-17 15:51:01.116254+07	cancelled by user	mqhtqwszecj5hpyoiqr	A05
3352	0cfd80ff	AGV02	go_to	18	cancelled	2026-06-17 15:44:01.385897+07	\N	2026-06-17 15:51:01.116254+07	cancelled by user	mqhtqwszecj5hpyoiqr	A05
3392	d0d35a35	AGV02	go_charge	\N	completed	2026-06-17 16:38:29.898926+07	2026-06-17 16:44:52.735382+07	2026-06-17 16:45:48.388726+07	off_route	mqhvoyr9beumsloftrw	A05
3429	070a4a0e	AGV01	go_charge	\N	completed	2026-06-18 08:40:20.666175+07	2026-06-18 08:40:20.666175+07	2026-06-18 08:40:28.289584+07	off_route	mqiu1wsd2rfx45z8osp	Sạc Pin
3451	c5c6dc4b	AGV01	go_to	96	cancelled	2026-06-19 11:30:58.789242+07	\N	2026-06-19 11:31:26.45547+07	cancelled by user	\N	\N
3450	76bc555e	AGV01	go_to	18	cancelled	2026-06-19 11:30:58.745674+07	\N	2026-06-19 11:31:26.45547+07	cancelled by user	\N	\N
3456	0ce5c73c	AGV01	go_to	18	queued	2026-06-19 11:59:39.18312+07	\N	\N	\N	\N	\N
3464	a2d2d126	AGV01	go_to	69	cancelled	2026-06-19 16:09:35.116125+07	\N	2026-06-19 16:09:52.570247+07	cancelled by user	\N	\N
3463	69876117	AGV01	go_to	96	cancelled	2026-06-19 16:09:35.085106+07	\N	2026-06-19 16:09:52.570247+07	cancelled by user	\N	\N
3492	72dc6a83	AGV01	go_to	17	completed	2026-06-23 14:16:17.984197+07	2026-06-23 14:17:03.129286+07	2026-06-23 14:17:16.443554+07	lifecycle:picking:confirmed	1a3yp8ogjcf7	Mobile 2 điểm
3471	8cf6a32f	AGV01	go_to	18	completed	2026-06-22 11:20:25.863951+07	2026-06-22 11:20:39.906056+07	2026-06-22 11:22:39.983864+07	lifecycle:picking:confirmed	\N	\N
3476	27142a93	AGV01	go_to	16	running	2026-06-22 11:36:00.947804+07	2026-06-22 11:36:50.752375+07	\N		\N	\N
3479	05afd978	AGV01	go_charge	13	completed	2026-06-22 11:40:27.256496+07	2026-06-22 11:40:27.257496+07	2026-06-22 11:40:41.965013+07	off_route	mqoq7n6javlrnc32a6o	Sạc Pin
3486	9c11986d	AGV01	go_to	8	cancelled	2026-06-22 11:55:34.673012+07	\N	2026-06-22 11:55:58.514646+07	cancelled by user	mqoqs344gikx5dgo7s5	Sạc Pin
3489	6be004a2	AGV01	go_charge	\N	completed	2026-06-23 13:55:28.49596+07	2026-06-23 13:55:28.49596+07	2026-06-23 13:55:42.81993+07		mqqaifhe4ok3rpas78j	Sạc Pin
3490	000d116b	AGV01	go_charge	\N	completed	2026-06-23 13:55:28.510967+07	2026-06-23 13:55:42.81993+07	2026-06-23 13:56:20.642316+07	charge_arrived	mqqaifhe4ok3rpas78j	Sạc Pin
3491	5f074fe4	AGV01	go_to	19	completed	2026-06-23 14:16:17.910182+07	2026-06-23 14:16:17.910182+07	2026-06-23 14:16:50.348232+07	lifecycle:picking:confirmed	1a3yp8ogjcf7	Mobile 2 điểm
3494	120cb7c0	AGV01	go_charge	\N	completed	2026-06-23 14:16:17.985235+07	2026-06-23 14:17:16.443554+07	2026-06-23 14:17:31.120276+07		1a3yp8ogjcf7	Mobile 2 điểm
3493	8e4f4715	AGV01	go_to	18	completed	2026-06-23 14:16:17.983197+07	2026-06-23 14:16:50.348232+07	2026-06-23 14:17:03.129286+07	lifecycle:picking:confirmed	1a3yp8ogjcf7	Mobile 2 điểm
3495	ae45f8c2	AGV01	go_charge	\N	completed	2026-06-23 14:17:16.457555+07	2026-06-23 14:17:31.121169+07	2026-06-23 14:18:14.681242+07	charge_arrived	1a3yp8ogjcf7	Mobile 2 điểm
3497	b9025803	AGV01	go_to	16	completed	2026-06-23 14:27:05.902112+07	2026-06-23 14:28:03.0852+07	2026-06-23 14:28:35.972411+07	lifecycle:picking:confirmed	yn3c3nr03wvr	Mobile 2 điểm
3501	80c0916d	AGV01	go_to	19	completed	2026-06-23 14:30:33.341908+07	2026-06-23 14:30:33.341908+07	2026-06-23 14:31:07.749175+07	lifecycle:picking:confirmed	hdptnv22eyhq	Mobile 3 điểm
2670	abcd4287	AGV02	go_to	17	completed	2026-06-13 11:53:14.801186+07	2026-06-13 11:53:14.801177+07	2026-06-13 11:57:54.027693+07	lifecycle:picking:confirmed	mqbvo1j2sp4iob7ybwd	dest_retry
2692	d40ee302	AGV02	go_to	19	completed	2026-06-13 12:21:30.620486+07	2026-06-13 12:21:30.62046+07	2026-06-13 12:22:05.951378+07	lifecycle:picking:confirmed	mqbwq7kgggn4wyoqgmn	dest_retry
2671	85549998	AGV02	go_charge	\N	completed	2026-06-13 11:57:54.056036+07	2026-06-13 11:58:08.448811+07	2026-06-13 11:58:56.789782+07	charge_arrived	mqbvo1j2sp4iob7ybwd	A06
2675	5198f9bc	AGV02	go_to	19	completed	2026-06-13 12:07:28.524504+07	2026-06-13 12:07:28.524488+07	2026-06-13 12:08:01.933381+07		mqbw90uncke8mwaw06p	A06
2702	3e878f29	AGV01	go_to	17	completed	2026-06-13 12:34:26.087282+07	2026-06-13 12:35:00.394139+07	2026-06-13 12:36:09.084171+07	lifecycle:picking:confirmed	mqbx7otp4uvxdxpq26	A06
2676	054983a2	AGV02	go_to	19	completed	2026-06-13 12:07:28.536272+07	2026-06-13 12:08:01.934158+07	2026-06-13 12:08:02.172852+07	dest_wait	mqbw90uncke8mwaw06p	A06
2672	56a144cb	AGV01	go_to	19	completed	2026-06-13 12:07:14.280951+07	2026-06-13 12:07:14.280941+07	2026-06-13 12:08:02.490629+07	lifecycle:picking:confirmed	mqbw8pu3bj01biky4w5	A06
2674	1904ce2d	AGV01	go_to	17	completed	2026-06-13 12:07:14.61656+07	2026-06-13 12:08:02.490837+07	2026-06-13 12:08:29.815572+07	lifecycle:picking:confirmed	mqbw8pu3bj01biky4w5	A06
2690	c6a3c22f	AGV02	go_to	17	completed	2026-06-13 12:20:50.417997+07	2026-06-13 12:22:05.951486+07	2026-06-13 12:22:32.756528+07		mqbwq7kgggn4wyoqgmn	A06
2673	27d703a7	AGV01	go_charge	\N	completed	2026-06-13 12:07:14.618304+07	2026-06-13 12:08:29.815697+07	2026-06-13 12:08:44.906883+07		mqbw8pu3bj01biky4w5	A06
2710	4a5ec4fd	AGV02	go_charge	14	completed	2026-06-13 12:39:41.024054+07	2026-06-13 12:39:41.025165+07	2026-06-13 12:39:57.207715+07		mqbx7wodj7b5ofy4xan	A06
2680	ad1b856a	AGV01	go_charge	\N	completed	2026-06-13 12:08:29.83218+07	2026-06-13 12:08:44.907603+07	2026-06-13 12:08:48.630862+07	yield_siding	mqbw8pu3bj01biky4w5	A06
2679	bbaa83d7	AGV02	go_to	19	completed	2026-06-13 12:08:10.771175+07	2026-06-13 12:08:10.771169+07	2026-06-13 12:08:48.990058+07	lifecycle:picking:confirmed	mqbw90uncke8mwaw06p	dest_retry
2681	0f923bc1	AGV01	go_to	8	completed	2026-06-13 12:08:48.632208+07	2026-06-13 12:08:48.632193+07	2026-06-13 12:09:35.917204+07	parked_siding	mqbw8pu3bj01biky4w5	yield_siding
2677	fa24759b	AGV02	go_to	17	cancelled	2026-06-13 12:07:28.557996+07	2026-06-13 12:08:48.99017+07	2026-06-13 12:12:30.7612+07	force-cancelled by user	mqbw90uncke8mwaw06p	A06
2678	dedc4cac	AGV02	go_charge	\N	cancelled	2026-06-13 12:07:28.559706+07	\N	2026-06-13 12:12:30.76136+07	cancelled by user	mqbw90uncke8mwaw06p	A06
2682	03a2bcb5	AGV02	go_charge	\N	completed	2026-06-13 12:12:37.869165+07	2026-06-13 12:12:37.86916+07	2026-06-13 12:13:28.07418+07		mqbwfnjlvfhn9073gee	Sạc Pin
2696	ef79e076	AGV02	go_to	17	completed	2026-06-13 12:22:05.976252+07	2026-06-13 12:22:32.75668+07	2026-06-13 12:22:52.480255+07		mqbwq7kgggn4wyoqgmn	A06
2683	a1c92f01	AGV02	go_charge	\N	completed	2026-06-13 12:12:37.8891+07	2026-06-13 12:13:28.074968+07	2026-06-13 12:14:02.621304+07	charge_arrived	mqbwfnjlvfhn9073gee	Sạc Pin
2684	680af074	AGV01	go_charge	\N	completed	2026-06-13 12:13:28.07676+07	2026-06-13 12:13:28.076752+07	2026-06-13 12:14:34.476216+07	charge_arrived	mqbw8pu3bj01biky4w5	yield_resume
2688	9db5e1b3	AGV02	go_to	19	completed	2026-06-13 12:20:50.387487+07	2026-06-13 12:20:50.38748+07	2026-06-13 12:21:18.941948+07		mqbwq7kgggn4wyoqgmn	A06
2705	81ffb8fa	AGV02	go_to	17	completed	2026-06-13 12:34:36.116415+07	2026-06-13 12:35:56.033854+07	2026-06-13 12:36:11.8735+07		mqbx7wodj7b5ofy4xan	A06
2689	01b7830c	AGV02	go_to	19	completed	2026-06-13 12:20:50.398182+07	2026-06-13 12:21:18.942575+07	2026-06-13 12:21:19.089896+07	dest_wait	mqbwq7kgggn4wyoqgmn	A06
2685	daefd533	AGV01	go_to	19	completed	2026-06-13 12:20:35.53269+07	2026-06-13 12:20:35.532681+07	2026-06-13 12:21:22.04573+07	lifecycle:picking:confirmed	mqbwpw2xfdddgaz9y6a	A06
2695	0e674317	AGV01	go_to	8	completed	2026-06-13 12:22:03.559167+07	2026-06-13 12:22:03.559155+07	2026-06-13 12:26:10.911345+07	parked_siding	mqbwpw2xfdddgaz9y6a	yield_siding
2687	ae782810	AGV01	go_to	17	completed	2026-06-13 12:20:35.699457+07	2026-06-13 12:21:22.04596+07	2026-06-13 12:21:40.84481+07	off_route	mqbwpw2xfdddgaz9y6a	A06
2693	9f73d546	AGV01	go_to	17	completed	2026-06-13 12:21:40.838854+07	2026-06-13 12:21:40.84836+07	2026-06-13 12:21:40.85628+07	already_at_dest	mqbwpw2xfdddgaz9y6a	A06
2697	d0de0946	AGV02	go_to	17	completed	2026-06-13 12:22:32.761471+07	2026-06-13 12:22:52.4811+07	2026-06-13 12:26:30.401124+07	lifecycle:picking:confirmed	mqbwq7kgggn4wyoqgmn	A06
2686	3bde9ff1	AGV01	go_charge	\N	completed	2026-06-13 12:20:35.700661+07	2026-06-13 12:21:40.856594+07	2026-06-13 12:21:59.726427+07		mqbwpw2xfdddgaz9y6a	A06
2716	d03c4b1b	AGV02	go_to	19	completed	2026-06-13 12:45:15.694429+07	2026-06-13 12:45:15.694413+07	2026-06-13 12:45:27.717832+07		mqbxlm7bhcpxvp8b96g	A06
2694	bcdcf02d	AGV01	go_charge	\N	completed	2026-06-13 12:21:40.877829+07	2026-06-13 12:21:59.727096+07	2026-06-13 12:22:03.557753+07	yield_siding	mqbwpw2xfdddgaz9y6a	A06
2691	a30c71e7	AGV02	go_charge	\N	completed	2026-06-13 12:20:50.418951+07	2026-06-13 12:26:30.40151+07	2026-06-13 12:27:20.357095+07	charge_arrived	mqbwq7kgggn4wyoqgmn	A06
2698	bff07db3	AGV01	go_charge	\N	cancelled	2026-06-13 12:26:28.503954+07	2026-06-13 12:26:28.50395+07	2026-06-13 12:27:39.868097+07	force-cancelled by user	mqbwpw2xfdddgaz9y6a	yield_resume
2699	dfc22e22	AGV01	go_charge	\N	completed	2026-06-13 12:27:50.097903+07	2026-06-13 12:27:50.097896+07	2026-06-13 12:28:42.240338+07	charge_arrived	mqbwz7fbubek5frkeyk	Sạc Pin
2700	35a78999	AGV01	go_to	19	completed	2026-06-13 12:34:25.920481+07	2026-06-13 12:34:25.920472+07	2026-06-13 12:35:00.393841+07	lifecycle:picking:confirmed	mqbx7otp4uvxdxpq26	A06
2711	f92dd4fc	AGV02	go_charge	\N	completed	2026-06-13 12:39:41.055608+07	2026-06-13 12:39:57.20824+07	2026-06-13 12:40:35.136028+07	charge_arrived	mqbx7wodj7b5ofy4xan	A06
2707	e8c36d1c	AGV02	go_to	17	completed	2026-06-13 12:35:56.04368+07	2026-06-13 12:36:11.874369+07	2026-06-13 12:39:06.441979+07	lifecycle:picking:confirmed	mqbx7wodj7b5ofy4xan	A06
2703	9320fe65	AGV02	go_to	19	completed	2026-06-13 12:34:36.081144+07	2026-06-13 12:34:36.08113+07	2026-06-13 12:35:07.381456+07		mqbx7wodj7b5ofy4xan	A06
2704	3d90902a	AGV02	go_to	19	completed	2026-06-13 12:34:36.09007+07	2026-06-13 12:35:07.38221+07	2026-06-13 12:35:56.033695+07	lifecycle:picking:confirmed	mqbx7wodj7b5ofy4xan	A06
2712	e71144e9	AGV01	go_charge	\N	completed	2026-06-13 12:39:55.258081+07	2026-06-13 12:39:55.258078+07	2026-06-13 12:42:00.059734+07	charge_arrived	mqbxeqyuwmqesurlho	Sạc Pin
2706	41255f05	AGV02	go_charge	\N	completed	2026-06-13 12:34:36.118676+07	2026-06-13 12:39:06.442086+07	2026-06-13 12:39:20.77044+07		mqbx7wodj7b5ofy4xan	A06
2708	41ab6baf	AGV02	go_charge	\N	completed	2026-06-13 12:39:06.455024+07	2026-06-13 12:39:20.771651+07	2026-06-13 12:39:34.169562+07	off_route	mqbx7wodj7b5ofy4xan	A06
2701	a29ead6f	AGV01	go_charge	\N	cancelled	2026-06-13 12:34:26.089368+07	2026-06-13 12:36:09.08423+07	2026-06-13 12:39:40.142446+07	force-cancelled by user	mqbx7otp4uvxdxpq26	A06
2709	bd0e1f5b	AGV02	go_charge	14	completed	2026-06-13 12:39:34.168729+07	2026-06-13 12:39:34.170536+07	2026-06-13 12:39:41.024446+07	off_route	mqbx7wodj7b5ofy4xan	A06
2720	671e3771	AGV02	go_to	19	completed	2026-06-13 12:45:27.850598+07	2026-06-13 12:45:46.974491+07	2026-06-13 12:46:16.307202+07	lifecycle:picking:confirmed	mqbxlm7bhcpxvp8b96g	A06
2718	3bb0209f	AGV02	go_to	17	completed	2026-06-13 12:45:15.732482+07	2026-06-13 12:46:16.307623+07	2026-06-13 12:46:32.221172+07		mqbxlm7bhcpxvp8b96g	A06
2713	2c6c343e	AGV01	go_to	19	completed	2026-06-13 12:45:04.984442+07	2026-06-13 12:45:04.984431+07	2026-06-13 12:45:36.90222+07	lifecycle:picking:confirmed	mqbxldx6u9k0n3ql42	A06
2717	7c1324e4	AGV02	go_to	19	completed	2026-06-13 12:45:15.704345+07	2026-06-13 12:45:27.718149+07	2026-06-13 12:45:46.973132+07		mqbxlm7bhcpxvp8b96g	A06
2715	f40cf7ff	AGV01	go_to	17	completed	2026-06-13 12:45:05.131644+07	2026-06-13 12:45:36.902283+07	2026-06-13 12:46:23.623378+07	lifecycle:picking:confirmed	mqbxldx6u9k0n3ql42	A06
2721	97b24734	AGV02	go_to	17	completed	2026-06-13 12:46:16.339502+07	2026-06-13 12:46:32.221615+07	2026-06-13 12:47:01.697934+07	lifecycle:picking:confirmed	mqbxlm7bhcpxvp8b96g	A06
2722	ac3508fc	AGV02	go_charge	\N	completed	2026-06-13 12:47:01.722621+07	2026-06-13 12:47:15.982551+07	2026-06-13 12:48:36.48417+07	charge_arrived	mqbxlm7bhcpxvp8b96g	A06
2719	025af157	AGV02	go_charge	\N	completed	2026-06-13 12:45:15.734111+07	2026-06-13 12:47:01.698157+07	2026-06-13 12:47:15.981696+07		mqbxlm7bhcpxvp8b96g	A06
2714	f2968d35	AGV01	go_charge	\N	completed	2026-06-13 12:45:05.132695+07	2026-06-13 12:46:23.623529+07	2026-06-13 12:48:13.243865+07	charge_arrived	mqbxldx6u9k0n3ql42	A06
2723	93a44984	AGV01	go_to	19	completed	2026-06-13 12:48:43.768489+07	2026-06-13 12:48:43.768483+07	2026-06-13 12:49:17.580552+07	lifecycle:picking:confirmed	mqbxq2rnvlttxr1ayq	A06
2725	b432edab	AGV01	go_charge	\N	completed	2026-06-13 12:48:43.781452+07	2026-06-13 12:49:49.602288+07	2026-06-13 12:50:04.587873+07		mqbxq2rnvlttxr1ayq	A06
2849	0401a64d	AGV01	go_charge	\N	completed	2026-06-15 11:54:40.087951+07	2026-06-15 11:55:42.589642+07	2026-06-15 11:55:57.803748+07		mqeqo94giwz8ex08tra	A06
2726	abfda1e9	AGV02	go_to	19	completed	2026-06-13 12:48:58.701006+07	2026-06-13 12:48:58.700993+07	2026-06-13 12:49:25.09474+07		mqbxqeabnl68pium5vc	A06
2730	59ae19e3	AGV01	go_charge	\N	completed	2026-06-13 12:49:49.623344+07	2026-06-13 12:50:04.588504+07	2026-06-13 12:50:08.30143+07	yield_siding	mqbxq2rnvlttxr1ayq	A06
2727	c7de8339	AGV02	go_to	19	completed	2026-06-13 12:48:58.708398+07	2026-06-13 12:49:25.095922+07	2026-06-13 12:50:08.435184+07	lifecycle:picking:confirmed	mqbxqeabnl68pium5vc	A06
2731	6dd811a2	AGV01	go_to	8	completed	2026-06-13 12:50:08.302875+07	2026-06-13 12:50:08.302864+07	2026-06-13 12:51:50.104283+07	parked_siding	mqbxq2rnvlttxr1ayq	yield_siding
2729	e284ac5a	AGV02	go_charge	\N	completed	2026-06-13 12:48:58.787044+07	2026-06-13 12:53:20.954301+07	2026-06-13 12:53:35.389652+07		mqbxqeabnl68pium5vc	A06
2733	2c40d478	AGV02	go_charge	\N	completed	2026-06-13 12:53:21.004983+07	2026-06-13 12:53:35.391316+07	2026-06-13 12:54:24.100065+07	charge_arrived	mqbxqeabnl68pium5vc	A06
2850	753a0c8f	AGV02	go_to	19	completed	2026-06-15 11:54:50.65168+07	2026-06-15 11:54:50.651664+07	2026-06-15 11:55:06.848146+07		mqeqohediemmfo77i	A06
2847	077e15aa	AGV01	go_to	19	completed	2026-06-15 11:54:39.939251+07	2026-06-15 11:54:39.93923+07	2026-06-15 11:55:13.400535+07	lifecycle:picking:confirmed	mqeqo94giwz8ex08tra	A06
3004	8d802373	AGV01	go_charge	\N	completed	2026-06-16 10:31:20.288014+07	2026-06-16 10:31:20.287996+07	2026-06-16 10:32:07.969855+07	charge_arrived	mqg34y1wko36tm9iqyj	Sạc Pin
2848	14bef704	AGV01	go_to	17	completed	2026-06-15 11:54:40.084444+07	2026-06-15 11:55:13.400634+07	2026-06-15 11:55:42.589324+07	lifecycle:picking:confirmed	mqeqo94giwz8ex08tra	A06
2852	bcee1cb8	AGV02	go_to	17	cancelled	2026-06-15 11:54:50.673655+07	2026-06-15 11:56:23.206307+07	2026-06-15 13:15:00.25164+07	force-cancelled by user	mqeqohediemmfo77i	A06
2855	8b117b84	AGV01	go_charge	\N	cancelled	2026-06-15 11:55:42.611535+07	2026-06-15 11:55:57.804907+07	2026-06-15 13:15:07.029098+07	force-cancelled by user	mqeqo94giwz8ex08tra	A06
3346	0a853caf	AGV01	go_charge	\N	cancelled	2026-06-17 15:43:37.105083+07	\N	2026-06-17 15:50:47.680915+07	cancelled by user	mqhtqe24m1idh8dw9u	A05
2857	eba6c825	AGV02	go_charge	\N	completed	2026-06-15 13:15:14.395703+07	2026-06-15 13:15:37.827382+07	2026-06-15 13:16:13.047874+07	charge_arrived	mqetjvepmigoyfqu2vp	Sạc Pin
3056	65c08df5	AGV01	go_to	19	completed	2026-06-16 11:27:43.434916+07	2026-06-16 11:27:43.436546+07	2026-06-16 11:27:43.44093+07	pickup_already_done	mqg4ip6rvwvjk57emj	A05
2922	9394d0ac	AGV02	go_to	19	completed	2026-06-16 09:09:21.211029+07	2026-06-16 09:09:21.211015+07	2026-06-16 09:09:54.223251+07		mqg07igt9gwenij5fm9	A06
2921	d78437af	AGV01	go_to	16	completed	2026-06-16 09:09:12.795539+07	2026-06-16 09:09:46.434187+07	2026-06-16 09:10:29.18537+07	lifecycle:picking:confirmed	mqg07bufsnhojl0b6d	A06
3240	137e3dea	AGV02	go_to	18	completed	2026-06-16 16:40:56.702735+07	2026-06-16 16:46:14.447264+07	2026-06-16 16:46:28.663953+07		mqggc9el0vuse3cpqro	A05
2924	73091c9e	AGV02	go_to	16	cancelled	2026-06-16 09:09:21.238111+07	\N	2026-06-16 09:12:05.10361+07	cancelled by user	mqg07igt9gwenij5fm9	A06
2927	a443bc40	AGV02	go_charge	\N	cancelled	2026-06-16 09:12:19.336265+07	2026-06-16 09:12:19.33626+07	2026-06-16 09:12:36.182448+07	force-cancelled by user	mqg0bbwmp3lyr8i75np	Sạc Pin
2926	2ff2bcaf	AGV01	go_charge	\N	completed	2026-06-16 09:10:29.206602+07	2026-06-16 09:10:43.922016+07	2026-06-16 09:13:41.969699+07	charge_arrived	mqg07bufsnhojl0b6d	A06
2929	8ca8c5e8	AGV02	go_charge	\N	cancelled	2026-06-16 09:14:06.344128+07	2026-06-16 09:14:06.344123+07	2026-06-16 09:14:17.936501+07	force-cancelled by user	mqg0dmh9w79rr1ylfpd	Sạc Pin
2981	82b64cf0	AGV01	go_to	19	completed	2026-06-16 10:22:08.640794+07	2026-06-16 10:22:08.640775+07	2026-06-16 10:22:41.738758+07	event:continue	mqg2t4d1jyp0cfcz6p	A02
3055	d9e063e9	AGV01	go_to	2	completed	2026-06-16 11:27:28.318963+07	2026-06-16 11:27:43.441915+07	2026-06-16 11:27:57.880155+07	off_route	mqg4ip6rvwvjk57emj	A05
2982	4b08aaa6	AGV01	go_to	18	completed	2026-06-16 10:22:08.821041+07	2026-06-16 10:23:27.234227+07	2026-06-16 10:23:34.564987+07		mqg2t4d1jyp0cfcz6p	A02
2991	e0f43100	AGV01	go_to	18	completed	2026-06-16 10:23:27.25234+07	2026-06-16 10:23:34.565397+07	2026-06-16 10:23:51.48117+07		mqg2t4d1jyp0cfcz6p	A02
3063	aa57aa0b	AGV01	go_to	5	cancelled	2026-06-16 11:28:33.459332+07	\N	2026-06-16 11:31:09.740015+07	cancelled by user	mqg4ip6rvwvjk57emj	A05
2993	06b571b7	AGV02	go_to	15	cancelled	2026-06-16 10:23:43.982395+07	2026-06-16 10:23:58.382368+07	2026-06-16 10:28:02.681591+07	force-cancelled by user	mqg2tcod8g59if87nv9	A02
2989	3f5ceefc	AGV02	go_charge	\N	cancelled	2026-06-16 10:22:19.451005+07	\N	2026-06-16 10:28:02.681826+07	cancelled by user	mqg2tcod8g59if87nv9	A02
2994	e4af037c	AGV01	go_charge	\N	cancelled	2026-06-16 10:28:13.720601+07	2026-06-16 10:28:13.720596+07	2026-06-16 10:28:34.950804+07	force-cancelled by user	mqg30y3on8fb7y96hj	Sạc Pin
2996	07ee9e4b	AGV01	go_charge	\N	completed	2026-06-16 10:28:45.932597+07	2026-06-16 10:28:45.932592+07	2026-06-16 10:29:01.324437+07		mqg31mydleeocql85eh	Sạc Pin
2997	7accf6c8	AGV01	go_charge	\N	cancelled	2026-06-16 10:28:45.942723+07	2026-06-16 10:29:01.324691+07	2026-06-16 10:30:03.245219+07	force-cancelled by user	mqg31mydleeocql85eh	Sạc Pin
3000	212427a8	AGV02	go_charge	\N	cancelled	2026-06-16 10:29:59.10295+07	2026-06-16 10:29:59.102932+07	2026-06-16 10:30:14.171867+07	force-cancelled by user	mqg337f03in1jxjzgag	Sạc Pin
3001	dbd42932	AGV02	go_charge	\N	completed	2026-06-16 10:30:19.423536+07	2026-06-16 10:30:19.423523+07	2026-06-16 10:30:33.840968+07		mqg33n2w5qw1kig567v	Sạc Pin
3236	b462b532	AGV01	go_to	17	completed	2026-06-16 16:40:38.173294+07	2026-06-16 16:45:49.254422+07	2026-06-16 16:46:42.84348+07	lifecycle:picking:confirmed	mqggbuwu3cpos7vdpfs	A05
3111	7039f18f	AGV01	go_to	96	completed	2026-06-16 13:59:10.822989+07	2026-06-16 13:59:22.536683+07	2026-06-16 14:00:13.41428+07	lifecycle:picking:confirmed	mqg9db1mma8mrrvp1aa	A05
3176	8b2142b8	AGV01	go_charge	\N	cancelled	2026-06-16 15:49:32.785978+07	2026-06-16 15:49:32.785978+07	2026-06-16 15:50:19.995581+07	force-cancelled by user	mqgei5wlbzpm1j3st49	Sạc Pin
3177	86e8e5bd	AGV01	go_charge	\N	completed	2026-06-16 15:50:27.050095+07	2026-06-16 15:50:27.050095+07	2026-06-16 15:50:41.537056+07		mqgejbsn8az6sznfykd	Sạc Pin
3178	a7c369a3	AGV01	go_charge	\N	cancelled	2026-06-16 15:50:27.060096+07	2026-06-16 15:50:41.537056+07	2026-06-16 16:02:04.289494+07	force-cancelled by user	mqgejbsn8az6sznfykd	Sạc Pin
3242	030a77c6	AGV02	go_to	15	queued	2026-06-16 16:40:56.710766+07	\N	\N	\N	mqggc9el0vuse3cpqro	A05
3235	98a4b304	AGV01	go_to	15	completed	2026-06-16 16:40:38.164295+07	2026-06-16 16:45:24.439722+07	2026-06-16 16:45:39.415228+07		mqggbuwu3cpos7vdpfs	A05
3248	8458f757	AGV01	go_to	15	completed	2026-06-16 16:45:24.463641+07	2026-06-16 16:45:39.416434+07	2026-06-16 16:45:49.254422+07	lifecycle:picking:confirmed	mqggbuwu3cpos7vdpfs	A05
3308	32f6e4b2	AGV01	go_charge	\N	completed	2026-06-17 15:23:53.515959+07	2026-06-17 15:29:38.426251+07	2026-06-17 15:29:53.70627+07		mqht10otruzwoswgsvq	A05
3318	64d0244b	AGV02	go_to	19	completed	2026-06-17 15:24:18.192616+07	2026-06-17 15:24:37.909111+07	2026-06-17 15:25:00.582349+07	lifecycle:picking:confirmed	mqht1i431tvwdr671ixh	A05
3307	f138944d	AGV01	go_to	17	completed	2026-06-17 15:23:53.50496+07	2026-06-17 15:24:28.403303+07	2026-06-17 15:25:14.528953+07	lifecycle:picking:confirmed	mqht10otruzwoswgsvq	A05
3320	c8794f44	AGV01	go_to	5	completed	2026-06-17 15:25:14.558098+07	2026-06-17 15:25:30.154955+07	2026-06-17 15:25:30.155942+07	already_at_dest	mqht10otruzwoswgsvq	A05
3347	99c5a115	AGV02	go_to	19	completed	2026-06-17 15:44:01.341446+07	2026-06-17 15:44:01.341446+07	2026-06-17 15:44:27.275657+07		mqhtqwszecj5hpyoiqr	A05
3409	e400247e	AGV01	go_to	19	completed	2026-06-18 08:12:38.299942+07	2026-06-18 08:12:38.299942+07	2026-06-18 08:13:26.628877+07	lifecycle:picking:confirmed	mqit2a1jo8v278sc1x	A05
3349	40655cbb	AGV02	go_to	16	cancelled	2026-06-17 15:44:01.381731+07	2026-06-17 15:45:01.391972+07	2026-06-17 15:51:01.115073+07	force-cancelled by user	mqhtqwszecj5hpyoiqr	A05
3351	832ddd8b	AGV02	go_to	15	cancelled	2026-06-17 15:44:01.38495+07	\N	2026-06-17 15:51:01.116254+07	cancelled by user	mqhtqwszecj5hpyoiqr	A05
3417	65fa7224	AGV02	go_to	17	completed	2026-06-18 08:13:16.212522+07	2026-06-18 08:13:59.304925+07	2026-06-18 08:14:31.639706+07	lifecycle:picking:confirmed	mqit33af6cot1unb2zx	A05
3420	332a52a5	AGV02	go_charge	\N	cancelled	2026-06-18 08:13:16.231332+07	\N	2026-06-18 08:40:06.864424+07	cancelled by user	mqit33af6cot1unb2zx	A05
3410	1faece0e	AGV01	go_to	16	completed	2026-06-18 08:12:38.384015+07	2026-06-18 08:13:26.628877+07	2026-06-18 08:14:10.915368+07	lifecycle:picking:confirmed	mqit2a1jo8v278sc1x	A05
3424	8077ca95	AGV02	go_to	15	completed	2026-06-18 08:14:31.725628+07	2026-06-18 08:14:46.999772+07	2026-06-18 08:15:26.064883+07	lifecycle:picking:confirmed	mqit33af6cot1unb2zx	A05
3412	d6faaa7d	AGV01	go_to	17	cancelled	2026-06-18 08:12:38.392069+07	\N	2026-06-18 08:40:12.398777+07	cancelled by user	mqit2a1jo8v278sc1x	A05
2724	5ba42da4	AGV01	go_to	17	completed	2026-06-13 12:48:43.78094+07	2026-06-13 12:49:17.580815+07	2026-06-13 12:49:49.602101+07	lifecycle:picking:confirmed	mqbxq2rnvlttxr1ayq	A06
2755	3fec7557	AGV01	go_charge	\N	cancelled	2026-06-15 10:07:36.332385+07	2026-06-15 10:07:36.332376+07	2026-06-15 10:08:10.647169+07	force-cancelled by user	mqemuknuumvfldsp5ua	Sạc Pin
2728	c7655a64	AGV02	go_to	17	completed	2026-06-13 12:48:58.78429+07	2026-06-13 12:50:08.435272+07	2026-06-13 12:53:20.954017+07	lifecycle:picking:confirmed	mqbxqeabnl68pium5vc	A06
2732	b578f1f2	AGV01	go_charge	\N	completed	2026-06-13 12:52:07.822707+07	2026-06-13 12:52:07.822697+07	2026-06-13 12:54:09.589617+07	charge_arrived	mqbxq2rnvlttxr1ayq	yield_resume
2740	b861b203	AGV02	go_charge	\N	queued	2026-06-13 12:55:27.007469+07	\N	\N	\N	mqbxypvfsji7dn6nv2	A06
2737	c4497d92	AGV02	go_to	19	completed	2026-06-13 12:55:26.966028+07	2026-06-13 12:55:26.966022+07	2026-06-13 12:55:57.602495+07		mqbxypvfsji7dn6nv2	A06
2756	4270757b	AGV01	go_charge	\N	cancelled	2026-06-15 10:07:42.62358+07	\N	2026-06-15 10:08:10.647396+07	cancelled by user	mqema2nwaol9k7l2xr5	yield_resume
2738	b4ba8f4a	AGV02	go_to	19	completed	2026-06-13 12:55:26.97336+07	2026-06-13 12:55:57.603948+07	2026-06-13 12:55:57.748545+07	dest_wait	mqbxypvfsji7dn6nv2	A06
2734	55999924	AGV01	go_to	19	completed	2026-06-13 12:55:13.654563+07	2026-06-13 12:55:13.654545+07	2026-06-13 12:56:01.501214+07	lifecycle:picking:confirmed	mqbxyfkujo7491somzr	A06
2736	45e4ecad	AGV01	go_to	17	completed	2026-06-13 12:55:13.899407+07	2026-06-13 12:56:01.501346+07	2026-06-13 12:56:38.758832+07	lifecycle:picking:confirmed	mqbxyfkujo7491somzr	A06
2741	9181090e	AGV02	go_to	19	completed	2026-06-13 12:56:09.644143+07	2026-06-13 12:56:09.64413+07	2026-06-13 12:56:47.55263+07	lifecycle:picking:confirmed	mqbxypvfsji7dn6nv2	dest_retry
2739	6bc65804	AGV02	go_to	17	running	2026-06-13 12:55:27.004451+07	2026-06-13 12:56:47.552695+07	\N		mqbxypvfsji7dn6nv2	A06
2735	273ae5eb	AGV01	go_charge	\N	completed	2026-06-13 12:55:13.902666+07	2026-06-13 12:56:38.759217+07	2026-06-13 12:56:53.724011+07		mqbxyfkujo7491somzr	A06
2757	df4b491b	AGV02	go_charge	\N	completed	2026-06-15 10:08:25.868146+07	2026-06-15 10:08:25.868141+07	2026-06-15 10:08:33.489823+07	off_route	mqemvmvoe5asc8l2w18	Sạc Pin
2742	dca78ee6	AGV01	go_charge	\N	completed	2026-06-13 12:56:38.797296+07	2026-06-13 12:56:53.724318+07	2026-06-13 12:56:54.284804+07	yield_siding	mqbxyfkujo7491somzr	A06
2743	43d29485	AGV01	go_to	16	running	2026-06-13 12:56:54.285703+07	\N	\N	\N	mqbxyfkujo7491somzr	yield_siding
2744	ec588111	AGV01	go_to	19	completed	2026-06-15 09:51:39.918798+07	2026-06-15 09:51:39.918776+07	2026-06-15 09:52:12.368673+07	lifecycle:picking:confirmed	mqema2nwaol9k7l2xr5	A06
2769	886a0eab	AGV02	go_to	19	completed	2026-06-15 10:36:05.876924+07	2026-06-15 10:36:05.876916+07	2026-06-15 10:36:17.87844+07		mqenv7qqn87zanqn4	A06
2747	042caf0e	AGV02	go_to	19	completed	2026-06-15 09:51:53.531664+07	2026-06-15 09:51:53.531655+07	2026-06-15 09:52:23.557733+07		mqemad6i7x9gjq2llbq	A06
2745	8d63e2db	AGV01	go_to	17	completed	2026-06-15 09:51:39.955505+07	2026-06-15 09:52:12.368783+07	2026-06-15 09:52:47.142913+07	lifecycle:picking:confirmed	mqema2nwaol9k7l2xr5	A06
2758	4b73d8d5	AGV02	go_charge	13	completed	2026-06-15 10:08:33.488783+07	2026-06-15 10:08:33.490139+07	2026-06-15 10:08:49.620782+07		mqemvmvoe5asc8l2w18	Sạc Pin
2748	56fb9ea8	AGV02	go_to	19	completed	2026-06-15 09:51:53.538624+07	2026-06-15 09:52:23.558982+07	2026-06-15 09:52:58.816803+07	lifecycle:picking:confirmed	mqemad6i7x9gjq2llbq	A06
2930	6e328de4	AGV01	go_to	19	completed	2026-06-16 09:24:55.421045+07	2026-06-16 09:24:55.421039+07	2026-06-16 09:25:27.295254+07	lifecycle:picking:confirmed	mqg0rjaf0o6iev2mwmpr	A06
2746	23ea7d9a	AGV01	go_charge	\N	completed	2026-06-15 09:51:39.957056+07	2026-06-15 09:52:47.143036+07	2026-06-15 09:53:02.197384+07		mqema2nwaol9k7l2xr5	A06
2751	f414d2cb	AGV01	go_charge	\N	completed	2026-06-15 09:52:47.155475+07	2026-06-15 09:53:02.199059+07	2026-06-15 09:53:05.522548+07	yield_siding	mqema2nwaol9k7l2xr5	A06
2752	9e92ffd8	AGV01	go_to	16	cancelled	2026-06-15 09:53:05.523549+07	2026-06-15 09:53:05.523536+07	2026-06-15 10:07:11.959945+07	force-cancelled by user	mqema2nwaol9k7l2xr5	yield_siding
2749	dea44503	AGV02	go_to	17	cancelled	2026-06-15 09:51:53.551321+07	2026-06-15 09:52:58.817082+07	2026-06-15 10:07:15.842587+07	force-cancelled by user	mqemad6i7x9gjq2llbq	A06
2750	e94a0525	AGV02	go_charge	\N	cancelled	2026-06-15 09:51:53.552068+07	\N	2026-06-15 10:07:15.843211+07	cancelled by user	mqemad6i7x9gjq2llbq	A06
2753	17530658	AGV02	go_charge	\N	completed	2026-06-15 10:07:26.057275+07	2026-06-15 10:07:26.057256+07	2026-06-15 10:07:42.62083+07		mqemucpul98ojxb6y7p	Sạc Pin
2759	80f25402	AGV02	go_charge	\N	completed	2026-06-15 10:08:33.514998+07	2026-06-15 10:08:49.621509+07	2026-06-15 10:09:01.27364+07	off_route	mqemvmvoe5asc8l2w18	Sạc Pin
2754	b7ede00d	AGV02	go_charge	\N	cancelled	2026-06-15 10:07:26.099697+07	2026-06-15 10:07:42.62206+07	2026-06-15 10:08:05.420969+07	force-cancelled by user	mqemucpul98ojxb6y7p	Sạc Pin
2760	1e614220	AGV02	go_charge	13	completed	2026-06-15 10:09:01.272433+07	2026-06-15 10:09:01.274809+07	2026-06-15 10:09:13.386226+07	off_route	mqemvmvoe5asc8l2w18	Sạc Pin
2761	5ba9c28e	AGV02	go_charge	13	completed	2026-06-15 10:09:13.386002+07	2026-06-15 10:09:13.386497+07	2026-06-15 10:09:28.258449+07		mqemvmvoe5asc8l2w18	Sạc Pin
2774	cffe7930	AGV01	go_charge	\N	completed	2026-06-15 10:36:57.35565+07	2026-06-15 10:37:12.412592+07	2026-06-15 10:37:16.104909+07	yield_siding	mqenv0dtxuepowp4my8	A06
2762	a6968136	AGV02	go_charge	\N	completed	2026-06-15 10:09:13.400551+07	2026-06-15 10:09:28.25912+07	2026-06-15 10:09:54.460142+07	charge_arrived	mqemvmvoe5asc8l2w18	Sạc Pin
2763	ea12c824	AGV01	go_charge	\N	cancelled	2026-06-15 10:09:27.806792+07	2026-06-15 10:09:27.806781+07	2026-06-15 10:09:57.395028+07	force-cancelled by user	mqemwyobo1vlfw6vn3m	Sạc Pin
2764	160fa3a0	AGV01	go_charge	\N	completed	2026-06-15 10:10:05.235737+07	2026-06-15 10:10:05.235731+07	2026-06-15 10:10:22.186335+07		mqemxrjy3hu9idkld03	Sạc Pin
2766	4661c6ef	AGV01	go_to	19	completed	2026-06-15 10:35:56.35609+07	2026-06-15 10:35:56.356073+07	2026-06-15 10:36:28.782332+07	lifecycle:picking:confirmed	mqenv0dtxuepowp4my8	A06
2765	89b59afb	AGV01	go_charge	\N	completed	2026-06-15 10:10:05.244455+07	2026-06-15 10:10:22.187072+07	2026-06-15 10:11:15.537883+07	charge_arrived	mqemxrjy3hu9idkld03	Sạc Pin
2770	e01067a2	AGV02	go_to	19	completed	2026-06-15 10:36:05.885328+07	2026-06-15 10:36:17.879087+07	2026-06-15 10:36:37.12098+07		mqenv7qqn87zanqn4	A06
2771	869d2e7d	AGV02	go_to	17	cancelled	2026-06-15 10:36:05.901383+07	2026-06-15 10:37:04.207451+07	2026-06-15 10:39:47.801122+07	force-cancelled by user	mqenv7qqn87zanqn4	A06
2768	589e6df7	AGV01	go_to	17	completed	2026-06-15 10:35:56.524346+07	2026-06-15 10:36:28.782476+07	2026-06-15 10:36:57.332301+07	lifecycle:picking:confirmed	mqenv0dtxuepowp4my8	A06
2772	2bd278a9	AGV02	go_charge	\N	cancelled	2026-06-15 10:36:05.902668+07	\N	2026-06-15 10:39:47.801572+07	cancelled by user	mqenv7qqn87zanqn4	A06
2773	e9879df5	AGV02	go_to	19	completed	2026-06-15 10:36:17.980034+07	2026-06-15 10:36:37.122234+07	2026-06-15 10:37:04.207314+07	lifecycle:picking:confirmed	mqenv7qqn87zanqn4	A06
2983	5b1e6947	AGV01	go_to	16	completed	2026-06-16 10:22:08.819839+07	2026-06-16 10:22:41.740186+07	2026-06-16 10:23:27.233626+07	event:continue	mqg2t4d1jyp0cfcz6p	A02
2767	053ae63e	AGV01	go_charge	\N	completed	2026-06-15 10:35:56.525278+07	2026-06-15 10:36:57.332772+07	2026-06-15 10:37:12.412012+07		mqenv0dtxuepowp4my8	A06
2992	cda070b1	AGV01	go_to	18	cancelled	2026-06-16 10:23:34.575302+07	2026-06-16 10:23:51.48272+07	2026-06-16 10:28:06.96189+07	force-cancelled by user	mqg2t4d1jyp0cfcz6p	A02
2851	d570901a	AGV02	go_to	19	completed	2026-06-15 11:54:50.658852+07	2026-06-15 11:55:06.849438+07	2026-06-15 11:55:26.305415+07		mqeqohediemmfo77i	A06
2853	d4cf94a6	AGV02	go_charge	\N	cancelled	2026-06-15 11:54:50.674826+07	\N	2026-06-15 13:15:00.25175+07	cancelled by user	mqeqohediemmfo77i	A06
2935	82a54548	AGV02	go_to	16	completed	2026-06-16 09:25:07.680114+07	2026-06-16 09:26:03.298538+07	2026-06-16 09:26:32.171002+07		mqg0rsqmxxb3ku08rpf	A06
2938	c03bb6b1	AGV02	go_to	16	completed	2026-06-16 09:26:32.17973+07	2026-06-16 09:26:49.915845+07	2026-06-16 09:26:49.921824+07	dest_wait	mqg0rsqmxxb3ku08rpf	A06
2931	240497fd	AGV01	go_to	16	completed	2026-06-16 09:24:55.459187+07	2026-06-16 09:25:27.295464+07	2026-06-16 09:26:50.924055+07	event:continue	mqg0rjaf0o6iev2mwmpr	A06
2986	0f251552	AGV02	go_to	19	completed	2026-06-16 10:22:19.412152+07	2026-06-16 10:22:30.375575+07	2026-06-16 10:22:53.814659+07		mqg2tcod8g59if87nv9	A02
3064	9a49635b	AGV01	go_charge	\N	cancelled	2026-06-16 11:48:50.348249+07	2026-06-16 11:48:50.348241+07	2026-06-16 11:49:06.099333+07	force-cancelled by user	mqg5wm1pj6kqe50pl8	Sạc Pin
2988	87eaaa0a	AGV02	go_to	15	completed	2026-06-16 10:22:19.449229+07	2026-06-16 10:23:43.962463+07	2026-06-16 10:23:58.3821+07		mqg2tcod8g59if87nv9	A02
3112	da0dde5a	AGV01	go_charge	\N	completed	2026-06-16 14:02:39.056569+07	2026-06-16 14:02:54.335768+07	2026-06-16 14:03:46.222462+07	charge_arrived	mqg9db1mma8mrrvp1aa	A05
3496	b8b5290c	AGV01	go_to	19	completed	2026-06-23 14:27:05.755342+07	2026-06-23 14:27:05.755342+07	2026-06-23 14:27:43.777546+07	lifecycle:picking:confirmed	yn3c3nr03wvr	Mobile 2 điểm
3499	766375a1	AGV01	go_charge	\N	completed	2026-06-23 14:27:05.903143+07	2026-06-23 14:28:35.973412+07	2026-06-23 14:28:50.092404+07		yn3c3nr03wvr	Mobile 2 điểm
3500	56545180	AGV01	go_charge	\N	completed	2026-06-23 14:28:35.997314+07	2026-06-23 14:28:50.093561+07	2026-06-23 14:30:10.131778+07	charge_arrived	yn3c3nr03wvr	Mobile 2 điểm
3504	5b1ca4b2	AGV01	go_to	15	completed	2026-06-23 14:30:33.350882+07	2026-06-23 14:31:37.308447+07	2026-06-23 14:31:51.744757+07		hdptnv22eyhq	Mobile 3 điểm
3506	54d81cc4	AGV01	go_to	15	completed	2026-06-23 14:31:37.327453+07	2026-06-23 14:31:51.744757+07	2026-06-23 14:33:14.143769+07	lifecycle:picking:confirmed	hdptnv22eyhq	Mobile 3 điểm
3498	e2da8b00	AGV01	go_to	18	completed	2026-06-23 14:27:05.901143+07	2026-06-23 14:27:43.778547+07	2026-06-23 14:28:03.0852+07	lifecycle:picking:confirmed	yn3c3nr03wvr	Mobile 2 điểm
3502	8ed86f9d	AGV01	go_to	18	completed	2026-06-23 14:30:33.349873+07	2026-06-23 14:31:07.749175+07	2026-06-23 14:31:23.821352+07	lifecycle:picking:confirmed	hdptnv22eyhq	Mobile 3 điểm
3507	4aab0892	AGV01	go_to	19	completed	2026-06-23 14:39:42.510978+07	2026-06-23 14:39:42.510978+07	2026-06-23 14:40:18.816485+07	lifecycle:picking:confirmed	m1f8qmls7oy6	Mobile → Tổ 1 — 18, Tổ 4 — 17, Tổ 5 — 16, Tổ 6 — 15
3509	ee3ad829	AGV01	go_to	17	completed	2026-06-23 14:39:42.592992+07	2026-06-23 14:40:34.938907+07	2026-06-23 14:40:48.684905+07	lifecycle:picking:confirmed	m1f8qmls7oy6	Mobile → Tổ 1 — 18, Tổ 4 — 17, Tổ 5 — 16, Tổ 6 — 15
3510	dcaee787	AGV01	go_charge	\N	completed	2026-06-23 14:39:42.595995+07	2026-06-23 14:41:42.072701+07	2026-06-23 14:42:39.395368+07	charge_arrived	m1f8qmls7oy6	Mobile → Tổ 1 — 18, Tổ 4 — 17, Tổ 5 — 16, Tổ 6 — 15
3526	f134ab84	AGV01	go_charge	\N	cancelled	2026-07-07 16:55:12.774981+07	\N	2026-07-07 16:55:18.535286+07	cancelled by user	mragahjcn050byr3hi	A06
3503	125cfdd6	AGV01	go_to	17	completed	2026-06-23 14:30:33.349873+07	2026-06-23 14:31:23.821352+07	2026-06-23 14:31:37.308447+07	lifecycle:picking:confirmed	hdptnv22eyhq	Mobile 3 điểm
3525	cd1cc400	AGV01	go_charge	\N	cancelled	2026-07-07 16:41:48.894455+07	2026-07-07 16:55:12.608207+07	2026-07-07 16:55:18.533287+07	force-cancelled by user	mragahjcn050byr3hi	A06
3505	104dd15a	AGV01	go_charge	\N	completed	2026-06-23 14:30:33.352888+07	2026-06-23 14:33:14.143769+07	2026-06-23 14:34:15.649344+07	charge_arrived	hdptnv22eyhq	Mobile 3 điểm
3508	6cacc833	AGV01	go_to	18	completed	2026-06-23 14:39:42.591996+07	2026-06-23 14:40:18.816485+07	2026-06-23 14:40:34.938907+07	lifecycle:picking:confirmed	m1f8qmls7oy6	Mobile → Tổ 1 — 18, Tổ 4 — 17, Tổ 5 — 16, Tổ 6 — 15
3527	244fff8b	AGV01	go_charge	\N	completed	2026-07-07 16:56:06.054227+07	2026-07-07 16:56:06.054227+07	2026-07-07 16:56:45.857154+07	off_route	mrah4n5dcr27juyoqyd	Sạc Pin
3511	be9a6b24	AGV01	go_to	16	completed	2026-06-23 14:39:42.592992+07	2026-06-23 14:40:48.684905+07	2026-06-23 14:41:27.316007+07	lifecycle:picking:confirmed	m1f8qmls7oy6	Mobile → Tổ 1 — 18, Tổ 4 — 17, Tổ 5 — 16, Tổ 6 — 15
3512	eba7477e	AGV01	go_to	15	completed	2026-06-23 14:39:42.594992+07	2026-06-23 14:41:27.316007+07	2026-06-23 14:41:42.072701+07	lifecycle:picking:confirmed	m1f8qmls7oy6	Mobile → Tổ 1 — 18, Tổ 4 — 17, Tổ 5 — 16, Tổ 6 — 15
3528	22a31888	AGV01	go_charge	13	completed	2026-07-07 16:56:45.857154+07	2026-07-07 16:56:45.858152+07	2026-07-07 16:58:26.474179+07	off_route	mrah4n5dcr27juyoqyd	Sạc Pin
3513	16a1c3a3	AGV01	go_to	19	completed	2026-06-26 15:14:49.18927+07	2026-06-26 15:14:49.18927+07	2026-06-26 15:15:31.653524+07	lifecycle:picking:confirmed	tmpx6vzatm30	Mobile → Tổ 1 — 18, Tổ 6 — 15
3515	bcac0038	AGV01	go_to	18	completed	2026-06-26 15:14:49.355028+07	2026-06-26 15:15:31.653524+07	2026-06-26 15:15:45.210524+07	lifecycle:picking:confirmed	tmpx6vzatm30	Mobile → Tổ 1 — 18, Tổ 6 — 15
3514	730d2f6c	AGV01	go_to	15	completed	2026-06-26 15:14:49.35603+07	2026-06-26 15:15:45.210524+07	2026-06-26 15:16:03.671134+07		tmpx6vzatm30	Mobile → Tổ 1 — 18, Tổ 6 — 15
3529	b1882f94	AGV01	go_charge	13	cancelled	2026-07-07 16:58:26.474179+07	2026-07-07 16:58:26.475231+07	2026-07-07 16:58:51.492852+07	force-cancelled by user	mrah4n5dcr27juyoqyd	Sạc Pin
3517	eaef86b5	AGV01	go_to	15	completed	2026-06-26 15:15:45.234502+07	2026-06-26 15:16:03.672141+07	2026-06-26 15:17:13.40436+07	lifecycle:picking:confirmed	tmpx6vzatm30	Mobile → Tổ 1 — 18, Tổ 6 — 15
3516	7acd8c00	AGV01	go_charge	\N	completed	2026-06-26 15:14:49.357273+07	2026-06-26 15:17:13.40436+07	2026-06-26 15:24:01.571823+07	charge_arrived	tmpx6vzatm30	Mobile → Tổ 1 — 18, Tổ 6 — 15
3518	0b9db0e1	AGV01	go_to	19	completed	2026-06-26 15:44:48.773488+07	2026-06-26 15:44:48.773488+07	2026-06-26 15:45:21.054156+07	lifecycle:picking:confirmed	duh7bgusqp5h	Mobile → Tổ 1 — 18
3520	27482b64	AGV01	go_to	18	completed	2026-06-26 15:44:49.071989+07	2026-06-26 15:45:21.054156+07	2026-06-26 15:45:35.041861+07	lifecycle:picking:confirmed	duh7bgusqp5h	Mobile → Tổ 1 — 18
3519	5e8f5942	AGV01	go_charge	\N	completed	2026-06-26 15:44:49.074524+07	2026-06-26 15:45:35.041861+07	2026-06-26 15:45:49.449558+07		duh7bgusqp5h	Mobile → Tổ 1 — 18
3540	857cb392	AGV01	go_to	19	completed	2026-07-08 09:20:28.198037+07	2026-07-08 09:20:28.198037+07	2026-07-08 09:21:23.009008+07	lifecycle:picking:confirmed	mrbgajs6xr2e1c317bi	A06
3521	cb369f86	AGV01	go_charge	\N	completed	2026-06-26 15:45:35.068156+07	2026-06-26 15:45:49.451564+07	2026-06-26 15:46:29.457551+07	charge_arrived	duh7bgusqp5h	Mobile → Tổ 1 — 18
3522	db4202ae	AGV01	go_to	19	completed	2026-07-07 16:32:39.143677+07	2026-07-07 16:32:39.143677+07	2026-07-07 16:40:50.953549+07	hook_lowered	mragahjcn050byr3hi	A06
3530	6ee42dcb	AGV01	go_to	19	completed	2026-07-08 08:54:39.592229+07	2026-07-08 08:54:39.592229+07	2026-07-08 08:57:51.665164+07	lifecycle:picking:confirmed	mrbfdcvch7dcvomshld	A06
3531	e357490e	AGV01	go_to	18	completed	2026-07-08 08:54:39.63676+07	2026-07-08 08:57:51.665164+07	2026-07-08 09:04:59.82327+07	lifecycle:picking:confirmed	mrbfdcvch7dcvomshld	A06
3523	67ff5521	AGV01	go_to	17	completed	2026-07-07 16:32:39.183041+07	2026-07-07 16:40:50.954598+07	2026-07-07 16:41:48.882441+07	hook_lowered	mragahjcn050byr3hi	A06
3546	8c3308ba	AGV01	go_to	19	completed	2026-07-08 09:24:29.022864+07	2026-07-08 09:24:29.022864+07	2026-07-08 09:25:09.076683+07	event:continue	mrbgfpl7c3tfknagmt	A06
3524	b3303eef	AGV01	go_charge	\N	completed	2026-07-07 16:32:39.184063+07	2026-07-07 16:41:48.883397+07	2026-07-07 16:55:12.607226+07	lifecycle:picking:confirmed	mragahjcn050byr3hi	A06
3550	667acdff	AGV01	go_to	5	completed	2026-07-08 09:26:37.626286+07	2026-07-08 09:26:37.62735+07	2026-07-08 09:27:38.013455+07		mrbgfpl7c3tfknagmt	A06
3532	5c5abff5	AGV01	go_charge	\N	completed	2026-07-08 08:54:39.63676+07	2026-07-08 09:04:59.82327+07	2026-07-08 09:05:14.436471+07	off_route	mrbfdcvch7dcvomshld	A06
3534	830b2014	AGV01	go_to	4	completed	2026-07-08 09:05:14.436471+07	2026-07-08 09:05:14.437679+07	2026-07-08 09:05:29.593295+07	off_route	mrbfdcvch7dcvomshld	A06
3536	53f9a1dd	AGV01	go_to	18	completed	2026-07-08 09:05:29.592367+07	2026-07-08 09:05:29.594304+07	2026-07-08 09:05:42.796853+07	off_route	mrbfdcvch7dcvomshld	A06
3538	67743871	AGV01	go_to	5	completed	2026-07-08 09:05:42.796853+07	2026-07-08 09:05:42.796853+07	2026-07-08 09:07:12.128494+07		mrbfdcvch7dcvomshld	A06
3541	c5cab91b	AGV01	go_to	18	completed	2026-07-08 09:20:28.215336+07	2026-07-08 09:21:23.010005+07	2026-07-08 09:21:48.077209+07	lifecycle:picking:confirmed	mrbgajs6xr2e1c317bi	A06
3539	6b95ae5b	AGV01	go_to	5	completed	2026-07-08 09:05:42.810228+07	2026-07-08 09:07:12.128494+07	2026-07-08 09:15:32.394024+07	lifecycle:picking:confirmed	mrbfdcvch7dcvomshld	A06
3537	6487a431	AGV01	go_to	18	completed	2026-07-08 09:05:29.601294+07	2026-07-08 09:15:32.394024+07	2026-07-08 09:15:39.900687+07	lifecycle:picking:confirmed	mrbfdcvch7dcvomshld	A06
3535	74442a8f	AGV01	go_to	4	completed	2026-07-08 09:05:14.702968+07	2026-07-08 09:15:39.900687+07	2026-07-08 09:15:50.048416+07	lifecycle:picking:confirmed	mrbfdcvch7dcvomshld	A06
3542	8203c6b6	AGV01	go_charge	\N	completed	2026-07-08 09:20:28.217844+07	2026-07-08 09:21:48.077209+07	2026-07-08 09:22:01.637725+07	off_route	mrbgajs6xr2e1c317bi	A06
3533	a0fe7fb1	AGV01	go_charge	\N	completed	2026-07-08 09:05:00.050355+07	2026-07-08 09:15:50.048416+07	2026-07-08 09:16:28.675189+07	charge_arrived	mrbfdcvch7dcvomshld	A06
3551	63e6308c	AGV01	go_to	5	completed	2026-07-08 09:26:37.713794+07	2026-07-08 09:27:38.014445+07	2026-07-08 09:27:50.834717+07	event:continue	mrbgfpl7c3tfknagmt	A06
3544	58c5b677	AGV01	go_to	4	completed	2026-07-08 09:22:01.636727+07	2026-07-08 09:22:01.638726+07	2026-07-08 09:22:25.209712+07		mrbgajs6xr2e1c317bi	A06
3545	a76b99de	AGV01	go_to	4	completed	2026-07-08 09:22:01.793732+07	2026-07-08 09:22:25.210714+07	2026-07-08 09:22:37.55834+07	lifecycle:picking:confirmed	mrbgajs6xr2e1c317bi	A06
3548	c93478e9	AGV01	go_to	17	completed	2026-07-08 09:24:29.076036+07	2026-07-08 09:25:09.076683+07	2026-07-08 09:26:25.09757+07	lifecycle:picking:confirmed	mrbgfpl7c3tfknagmt	A06
3543	57cb6cae	AGV01	go_charge	\N	completed	2026-07-08 09:21:48.096646+07	2026-07-08 09:22:37.55834+07	2026-07-08 09:23:13.936841+07	charge_arrived	mrbgajs6xr2e1c317bi	A06
3547	de5e16e9	AGV01	go_charge	\N	completed	2026-07-08 09:24:29.077055+07	2026-07-08 09:26:25.09757+07	2026-07-08 09:26:37.626286+07	off_route	mrbgfpl7c3tfknagmt	A06
3553	a7e95a08	AGV01	go_charge	\N	completed	2026-07-08 09:36:14.260137+07	2026-07-08 09:37:19.821643+07	2026-07-08 09:37:32.421269+07	off_route	mrbgutqibmgkwpet4ci	A06
3552	d8a46e3c	AGV01	go_to	19	completed	2026-07-08 09:36:14.225657+07	2026-07-08 09:36:14.225657+07	2026-07-08 09:36:51.626955+07	event:continue	mrbgutqibmgkwpet4ci	A06
3549	6d3c49ca	AGV01	go_charge	\N	completed	2026-07-08 09:26:25.119613+07	2026-07-08 09:27:50.834717+07	2026-07-08 09:28:32.440461+07	charge_arrived	mrbgfpl7c3tfknagmt	A06
3556	37c14e26	AGV01	go_to	5	completed	2026-07-08 09:37:32.421269+07	2026-07-08 09:37:32.422719+07	2026-07-08 09:43:14.90853+07	lifecycle:delivering:confirmed	mrbgutqibmgkwpet4ci	A06
3554	81917c07	AGV01	go_to	17	completed	2026-07-08 09:36:14.259138+07	2026-07-08 09:36:51.626955+07	2026-07-08 09:37:19.820638+07	lifecycle:delivering:confirmed	mrbgutqibmgkwpet4ci	A06
3557	1ce97b6a	AGV01	go_charge	13	completed	2026-07-08 09:44:02.965172+07	2026-07-08 09:44:02.965172+07	2026-07-08 09:44:52.787278+07	off_route	mrbgutqibmgkwpet4ci	A06
3555	69d203de	AGV01	go_charge	\N	completed	2026-07-08 09:37:19.88847+07	2026-07-08 09:43:14.90853+07	2026-07-08 09:44:02.965172+07	off_route	mrbgutqibmgkwpet4ci	A06
3558	0d07e616	AGV01	go_charge	13	completed	2026-07-08 09:44:52.784839+07	2026-07-08 09:44:52.78863+07	2026-07-08 09:45:33.23309+07	off_route	mrbgutqibmgkwpet4ci	A06
3559	d318a270	AGV01	go_charge	13	cancelled	2026-07-08 09:45:33.232093+07	2026-07-08 09:45:33.234089+07	2026-07-08 09:45:33.747078+07	force-cancelled by user	mrbgutqibmgkwpet4ci	A06
3560	6d9fb069	AGV01	go_to	19	completed	2026-07-08 09:54:40.476872+07	2026-07-08 09:54:40.476872+07	2026-07-08 09:55:37.941951+07	event:continue	mrbhijbiab4nyafex2g	A06
3562	ae866f6f	AGV01	go_to	18	completed	2026-07-08 09:54:40.513708+07	2026-07-08 09:55:37.942956+07	2026-07-08 09:55:58.336141+07	lifecycle:delivering:confirmed	mrbhijbiab4nyafex2g	A06
3561	348c509e	AGV01	go_charge	\N	completed	2026-07-08 09:54:40.516321+07	2026-07-08 09:55:58.336141+07	2026-07-08 09:56:11.786551+07	off_route	mrbhijbiab4nyafex2g	A06
3564	b2a32f5b	AGV01	go_to	4	completed	2026-07-08 09:56:11.785536+07	2026-07-08 09:56:11.787557+07	2026-07-08 09:56:54.046552+07	lifecycle:delivering:confirmed	mrbhijbiab4nyafex2g	A06
3563	6b13f378	AGV01	go_charge	\N	cancelled	2026-07-08 09:55:58.3554+07	2026-07-08 09:56:54.046552+07	2026-07-08 09:57:40.681381+07	force-cancelled by user	mrbhijbiab4nyafex2g	A06
3565	a2b759c4	AGV01	go_to	19	completed	2026-07-08 13:39:36.48928+07	2026-07-08 13:39:36.48928+07	2026-07-08 13:40:22.050465+07	event:continue	mrbpjsvpimw494m7cxa	A06
3567	4b7f42af	AGV01	go_to	18	completed	2026-07-08 13:39:36.789824+07	2026-07-08 13:40:22.051464+07	2026-07-08 13:40:35.863209+07	hook_raised	mrbpjsvpimw494m7cxa	A06
3566	bb23372b	AGV01	go_charge	\N	failed	2026-07-08 13:39:36.791339+07	2026-07-08 13:40:35.865223+07	2026-07-08 13:40:35.894124+07	'str' object has no attribute 'get'	mrbpjsvpimw494m7cxa	A06
3568	3814f7e6	AGV01	go_charge	\N	failed	2026-07-08 13:44:27.547836+07	2026-07-08 13:44:27.547836+07	2026-07-08 13:44:27.554851+07	'str' object has no attribute 'get'	mrbpq1ifr0wsizgliwa	Sạc Pin
3569	3f66d5a8	AGV01	go_charge	\N	running	2026-07-08 13:44:41.837295+07	\N	\N	\N	mrbpqciw1s7cl386912	Sạc Pin
3570	f3502e7e	AGV01	go_to	19	completed	2026-07-08 14:09:00.902679+07	2026-07-08 14:09:00.902679+07	2026-07-08 14:09:46.816397+07	event:continue	mrbqlmd4m19m0bb8efg	A06
3572	e8c18a16	AGV01	go_to	18	completed	2026-07-08 14:09:00.931835+07	2026-07-08 14:09:46.817394+07	2026-07-08 14:10:00.334506+07	hook_raised	mrbqlmd4m19m0bb8efg	A06
3571	e719bc00	AGV01	go_charge	\N	completed	2026-07-08 14:09:00.932836+07	2026-07-08 14:10:00.335515+07	2026-07-08 14:10:14.727321+07	off_route	mrbqlmd4m19m0bb8efg	A06
3574	71b8d0c3	AGV01	go_to	4	completed	2026-07-08 14:10:14.726303+07	2026-07-08 14:10:14.728368+07	2026-07-08 14:10:53.275173+07	hook_already_raised	mrbqlmd4m19m0bb8efg	A06
3573	d7bf4434	AGV01	go_charge	\N	completed	2026-07-08 14:10:00.348038+07	2026-07-08 14:10:53.276196+07	2026-07-08 14:11:37.017273+07	charge_arrived	mrbqlmd4m19m0bb8efg	A06
3577	8e1a638b	AGV01	go_to	15	cancelled	2026-07-08 14:43:14.834229+07	\N	2026-07-08 14:43:21.539406+07	cancelled by user	\N	\N
3576	55a736fe	AGV01	go_to	19	cancelled	2026-07-08 14:43:14.834229+07	\N	2026-07-08 14:43:21.539406+07	cancelled by user	\N	\N
3582	6e2dc73a	AGV01	go_to	15	completed	2026-07-08 14:45:32.071456+07	2026-07-08 14:46:23.458664+07	2026-07-08 14:47:07.795949+07	event:continue	\N	\N
3575	d7e88ba7	AGV01	go_charge	\N	cancelled	2026-07-08 14:43:14.834229+07	\N	2026-07-08 14:43:21.539406+07	cancelled by user	\N	\N
3581	f562fa4f	AGV01	go_to	19	completed	2026-07-08 14:45:32.06846+07	2026-07-08 14:47:07.796949+07	2026-07-08 14:48:05.60853+07	event:continue	\N	\N
3579	704bf9de	AGV01	go_to	18	cancelled	2026-07-08 14:43:15.233151+07	\N	2026-07-08 14:43:21.539406+07	cancelled by user	\N	\N
3580	bc4e1e2b	AGV01	go_charge	\N	completed	2026-07-08 14:45:32.065345+07	2026-07-08 14:48:05.609555+07	2026-07-08 14:48:35.813012+07	charge_arrived	\N	\N
3583	a2351f27	AGV01	go_to	18	completed	2026-07-08 14:45:32.073472+07	2026-07-08 14:45:32.123348+07	2026-07-08 14:46:09.874477+07	event:continue	\N	\N
3589	979ca574	AGV01	go_to	18	cancelled	2026-07-08 15:19:22.412661+07	\N	2026-07-08 15:20:09.415908+07	cancelled by user	\N	\N
3588	4978f443	AGV01	go_to	18	cancelled	2026-07-08 15:19:21.978847+07	2026-07-08 15:19:21.979851+07	2026-07-08 15:20:09.415908+07	force-cancelled by user	\N	\N
3587	f20c4d49	AGV01	go_to	15	cancelled	2026-07-08 15:19:21.978847+07	\N	2026-07-08 15:20:09.415908+07	cancelled by user	\N	\N
3585	a67e680c	AGV01	go_to	19	cancelled	2026-07-08 15:19:21.978847+07	\N	2026-07-08 15:20:09.415908+07	cancelled by user	\N	\N
3586	afb594f2	AGV01	go_charge	\N	cancelled	2026-07-08 15:19:21.977853+07	\N	2026-07-08 15:20:09.415908+07	cancelled by user	\N	\N
3591	ba4f104a	AGV01	go_to	19	cancelled	2026-07-08 15:32:59.308323+07	\N	2026-07-08 15:34:36.088385+07	cancelled by user	\N	\N
3593	df02ee18	AGV01	go_to	18	cancelled	2026-07-08 15:32:59.308323+07	2026-07-08 15:32:59.308323+07	2026-07-08 15:34:36.087003+07	force-cancelled by user	\N	\N
3592	e39f20ab	AGV01	go_to	15	cancelled	2026-07-08 15:32:59.308323+07	\N	2026-07-08 15:34:36.088385+07	cancelled by user	\N	\N
3594	ac012ef1	AGV01	go_to	18	cancelled	2026-07-08 15:32:59.808349+07	\N	2026-07-08 15:34:36.088385+07	cancelled by user	\N	\N
3590	1fcc8d72	AGV01	go_charge	\N	cancelled	2026-07-08 15:32:59.308323+07	\N	2026-07-08 15:34:36.088385+07	cancelled by user	\N	\N
3597	7fd0fbdc	AGV01	go_to	18	completed	2026-07-08 15:40:07.828413+07	2026-07-08 15:40:07.829413+07	2026-07-08 15:41:02.58472+07	event:continue	\N	\N
3624	e1e7f2fe	AGV02	go_to	16	cancelled	2026-07-09 08:40:30.121338+07	\N	2026-07-09 08:40:38.024679+07	cancelled by user	\N	\N
3599	7c548000	AGV01	go_to	18	completed	2026-07-08 15:40:08.305074+07	2026-07-08 15:41:02.585236+07	2026-07-08 15:41:16.052351+07	hook_raised	\N	\N
3598	b4046052	AGV01	go_to	15	completed	2026-07-08 15:40:07.828413+07	2026-07-08 15:41:16.053382+07	2026-07-08 15:41:53.588343+07	event:continue	\N	\N
3622	dca03910	AGV02	go_to	64	cancelled	2026-07-09 08:40:30.093292+07	\N	2026-07-09 08:40:38.024679+07	cancelled by user	\N	\N
3596	4bb41e3d	AGV01	go_to	19	completed	2026-07-08 15:40:07.828413+07	2026-07-08 15:41:53.588343+07	2026-07-08 15:42:35.61678+07	hook_raised	\N	\N
3621	83ebc753	AGV02	go_to	19	cancelled	2026-07-09 08:40:30.093292+07	\N	2026-07-09 08:40:38.024679+07	cancelled by user	\N	\N
3595	fcd6e0c7	AGV01	go_charge	\N	completed	2026-07-08 15:40:07.826414+07	2026-07-08 15:42:35.618781+07	2026-07-08 15:43:13.456716+07	charge_arrived	\N	\N
3601	f6b6086d	AGV01	go_to	19	cancelled	2026-07-08 15:47:48.244733+07	\N	2026-07-08 15:49:42.163337+07	cancelled by user	\N	\N
3602	b86854a5	AGV01	go_to	18	cancelled	2026-07-08 15:47:48.245738+07	2026-07-08 15:47:48.245738+07	2026-07-08 15:49:42.163337+07	force-cancelled by user	\N	\N
3603	5a166c45	AGV01	go_to	15	cancelled	2026-07-08 15:47:48.245738+07	\N	2026-07-08 15:49:42.163337+07	cancelled by user	\N	\N
3604	fb2e4e8c	AGV01	go_to	18	cancelled	2026-07-08 15:47:48.67859+07	\N	2026-07-08 15:49:42.163337+07	cancelled by user	\N	\N
3600	ceeabf37	AGV01	go_charge	\N	cancelled	2026-07-08 15:47:48.244733+07	\N	2026-07-08 15:49:42.163337+07	cancelled by user	\N	\N
3620	4575ab2a	AGV02	go_charge	\N	cancelled	2026-07-09 08:40:30.093292+07	\N	2026-07-09 08:40:38.024679+07	cancelled by user	\N	\N
3623	9cda8ed0	AGV02	go_to	16	cancelled	2026-07-09 08:40:30.093292+07	2026-07-09 08:40:30.093292+07	2026-07-09 08:40:38.024679+07	force-cancelled by user	\N	\N
3607	ed12a78e	AGV01	go_to	18	completed	2026-07-08 15:54:28.403491+07	2026-07-08 15:54:28.403491+07	2026-07-08 15:55:16.43025+07	event:continue	\N	\N
3609	24fc457c	AGV01	go_to	18	completed	2026-07-08 15:54:28.849296+07	2026-07-08 15:55:16.431329+07	2026-07-08 15:55:30.030292+07	hook_raised	\N	\N
3608	f455c8fb	AGV01	go_to	15	completed	2026-07-08 15:54:28.403491+07	2026-07-08 15:55:30.031304+07	2026-07-08 15:56:15.977956+07	event:continue	\N	\N
3606	882f0b7e	AGV01	go_to	19	completed	2026-07-08 15:54:28.40249+07	2026-07-08 15:56:15.97898+07	2026-07-08 15:56:57.958703+07	hook_raised	\N	\N
3605	1743c3d5	AGV01	go_charge	\N	completed	2026-07-08 15:54:28.40249+07	2026-07-08 15:56:57.958703+07	2026-07-08 15:57:33.788703+07	charge_arrived	\N	\N
3612	c9f5baeb	AGV01	go_to	18	cancelled	2026-07-08 15:59:18.969703+07	2026-07-08 15:59:18.970699+07	2026-07-08 16:51:41.679434+07	force-cancelled by user	\N	\N
3614	503918eb	AGV01	go_to	18	cancelled	2026-07-08 15:59:19.027522+07	\N	2026-07-08 16:51:41.680378+07	cancelled by user	\N	\N
3613	a2ca71ea	AGV01	go_charge	\N	cancelled	2026-07-08 15:59:18.968698+07	\N	2026-07-08 16:51:41.680378+07	cancelled by user	\N	\N
3611	beb59c11	AGV01	go_to	15	cancelled	2026-07-08 15:59:18.969703+07	\N	2026-07-08 16:51:41.680378+07	cancelled by user	\N	\N
3610	2fe01681	AGV01	go_to	19	cancelled	2026-07-08 15:59:18.968698+07	\N	2026-07-08 16:51:41.680378+07	cancelled by user	\N	\N
3619	9bacbe6a	AGV02	go_to	16	cancelled	2026-07-09 08:39:26.224355+07	\N	2026-07-09 08:39:38.401506+07	cancelled by user	\N	\N
3618	e86b4406	AGV02	go_to	16	cancelled	2026-07-09 08:39:25.828647+07	2026-07-09 08:39:25.828647+07	2026-07-09 08:39:38.401506+07	force-cancelled by user	\N	\N
3617	75dd1ee2	AGV02	go_to	64	cancelled	2026-07-09 08:39:25.827639+07	\N	2026-07-09 08:39:38.401506+07	cancelled by user	\N	\N
3616	525d22d1	AGV02	go_to	19	cancelled	2026-07-09 08:39:25.827639+07	\N	2026-07-09 08:39:38.401506+07	cancelled by user	\N	\N
3615	4d8070e8	AGV02	go_charge	\N	cancelled	2026-07-09 08:39:25.827639+07	\N	2026-07-09 08:39:38.401506+07	cancelled by user	\N	\N
3628	a78ab6ea	AGV01	go_to	16	cancelled	2026-07-09 08:41:07.498463+07	2026-07-09 08:41:07.498463+07	2026-07-09 08:41:21.80335+07	force-cancelled by user	\N	\N
3629	dbdabeb3	AGV01	go_to	16	cancelled	2026-07-09 08:41:07.555469+07	\N	2026-07-09 08:41:21.80335+07	cancelled by user	\N	\N
3627	e225a6e3	AGV01	go_to	64	cancelled	2026-07-09 08:41:07.498463+07	\N	2026-07-09 08:41:21.80335+07	cancelled by user	\N	\N
3625	664faab0	AGV01	go_charge	\N	cancelled	2026-07-09 08:41:07.497461+07	\N	2026-07-09 08:41:21.80335+07	cancelled by user	\N	\N
3626	801c3cf0	AGV01	go_to	19	cancelled	2026-07-09 08:41:07.497461+07	\N	2026-07-09 08:41:21.80335+07	cancelled by user	\N	\N
3636	9fb5f4c2	AGV01	go_charge	\N	completed	2026-07-09 09:05:44.345514+07	2026-07-09 09:05:44.345514+07	2026-07-09 09:06:11.976818+07	charge_arrived	mrcv7gg6868xf32m4bl	Sạc Pin
3633	6e276fc9	AGV01	go_to	16	completed	2026-07-09 08:52:56.432808+07	2026-07-09 08:52:56.432808+07	2026-07-09 08:55:43.955065+07	event:continue	\N	\N
3634	2150b17d	AGV01	go_to	16	completed	2026-07-09 08:52:56.862882+07	2026-07-09 08:55:43.957078+07	2026-07-09 08:56:13.483403+07	hook_raised	\N	\N
3631	13e22bb2	AGV01	go_to	64	completed	2026-07-09 08:52:56.432808+07	2026-07-09 08:56:13.48439+07	2026-07-09 08:56:59.645073+07	hook_already_raised	\N	\N
3635	0929b949	AGV01	go_to	64	cancelled	2026-07-09 08:56:13.554179+07	2026-07-09 08:56:59.646072+07	2026-07-09 09:05:35.694447+07	force-cancelled by user	\N	\N
3632	6ab04439	AGV01	go_to	19	cancelled	2026-07-09 08:52:56.431794+07	\N	2026-07-09 09:05:35.694447+07	cancelled by user	\N	\N
3630	20ce7d8c	AGV01	go_charge	\N	cancelled	2026-07-09 08:52:56.431794+07	\N	2026-07-09 09:05:35.694447+07	cancelled by user	\N	\N
3644	1ab67b74	AGV01	go_to	64	cancelled	2026-07-10 08:29:45.766215+07	\N	2026-07-10 08:31:15.603381+07	cancelled by user	\N	\N
3641	182d3665	AGV01	go_to	16	cancelled	2026-07-10 08:24:42.795248+07	\N	2026-07-10 08:26:19.941861+07	cancelled by user	\N	\N
3640	3244032c	AGV01	go_to	16	cancelled	2026-07-10 08:24:42.293326+07	2026-07-10 08:24:42.293326+07	2026-07-10 08:26:19.941861+07	force-cancelled by user	\N	\N
3639	2e1a10b1	AGV01	go_to	64	cancelled	2026-07-10 08:24:42.293326+07	\N	2026-07-10 08:26:19.941861+07	cancelled by user	\N	\N
3638	5381c16d	AGV01	go_charge	\N	cancelled	2026-07-10 08:24:42.293326+07	\N	2026-07-10 08:26:19.941861+07	cancelled by user	\N	\N
3637	1564aac1	AGV01	go_to	17	cancelled	2026-07-10 08:24:42.293326+07	\N	2026-07-10 08:26:19.941861+07	cancelled by user	\N	\N
3645	ff55dfc2	AGV01	go_to	16	cancelled	2026-07-10 08:29:45.766215+07	2026-07-10 08:29:45.766215+07	2026-07-10 08:31:15.602388+07	force-cancelled by user	\N	\N
3642	d1731691	AGV01	go_charge	\N	cancelled	2026-07-10 08:29:45.766215+07	\N	2026-07-10 08:31:15.603381+07	cancelled by user	\N	\N
3646	57b56a79	AGV01	go_to	16	cancelled	2026-07-10 08:29:46.11362+07	\N	2026-07-10 08:31:15.603381+07	cancelled by user	\N	\N
3643	b81ef83e	AGV01	go_to	17	cancelled	2026-07-10 08:29:45.766215+07	\N	2026-07-10 08:31:15.603381+07	cancelled by user	\N	\N
3649	6d504990	AGV02	go_to	64	completed	2026-07-10 08:31:28.399182+07	2026-07-10 08:32:44.745987+07	2026-07-10 08:33:38.368277+07	hook_already_raised	\N	\N
3650	ed1a0de5	AGV02	go_to	16	completed	2026-07-10 08:31:28.400183+07	2026-07-10 08:31:28.400183+07	2026-07-10 08:32:14.892556+07	event:continue	\N	\N
3651	21de559b	AGV02	go_to	16	completed	2026-07-10 08:31:28.448719+07	2026-07-10 08:32:14.893579+07	2026-07-10 08:32:44.744982+07	hook_raised	\N	\N
3652	22c45a92	AGV02	go_to	64	cancelled	2026-07-10 08:32:44.768596+07	2026-07-10 08:33:38.368277+07	2026-07-10 08:36:04.822396+07	force-cancelled by user	\N	\N
3655	120ba281	AGV01	go_charge	\N	cancelled	2026-07-10 08:37:29.941878+07	\N	2026-07-10 08:37:38.507299+07	cancelled by user	\N	\N
3647	d17cd661	AGV02	go_charge	\N	cancelled	2026-07-10 08:31:28.398182+07	\N	2026-07-10 08:36:04.822396+07	cancelled by user	\N	\N
3648	6fac79ea	AGV02	go_to	17	cancelled	2026-07-10 08:31:28.399182+07	\N	2026-07-10 08:36:04.822396+07	cancelled by user	\N	\N
3661	9c5ee222	AGV02	go_to	16	cancelled	2026-07-10 08:37:56.582244+07	\N	2026-07-10 08:48:40.167706+07	cancelled by user	\N	\N
3653	b3ecd39d	AGV02	go_charge	\N	completed	2026-07-10 08:36:13.987998+07	2026-07-10 08:36:13.987998+07	2026-07-10 08:36:50.257438+07	charge_arrived	mre9ld3v8q5m706ivu4	Sạc Pin
3654	7c8cf2a0	AGV01	go_to	19	cancelled	2026-07-10 08:37:29.941878+07	\N	2026-07-10 08:37:38.507299+07	cancelled by user	\N	\N
3663	11a534a7	AGV02	go_to	17	cancelled	2026-07-10 08:37:56.615075+07	\N	2026-07-10 08:48:40.167706+07	cancelled by user	\N	\N
3656	fcc20b16	AGV01	go_to	16	cancelled	2026-07-10 08:37:29.941878+07	\N	2026-07-10 08:37:38.507299+07	cancelled by user	\N	\N
3657	07504ae3	AGV01	go_to	17	cancelled	2026-07-10 08:37:29.942875+07	2026-07-10 08:37:29.942875+07	2026-07-10 08:37:38.506282+07	force-cancelled by user	\N	\N
3658	b4ca975f	AGV01	go_to	17	cancelled	2026-07-10 08:37:30.289973+07	\N	2026-07-10 08:37:38.507299+07	cancelled by user	\N	\N
3696	b607e41e	AGV01	go_charge	\N	completed	2026-07-10 10:25:52.90999+07	2026-07-10 10:29:35.165121+07	2026-07-10 10:30:21.836752+07	charge_arrived	\N	\N
3662	52392320	AGV02	go_to	17	cancelled	2026-07-10 08:37:56.582244+07	2026-07-10 08:37:56.582244+07	2026-07-10 08:48:40.167706+07	force-cancelled by user	\N	\N
3659	795bb4fa	AGV02	go_charge	\N	cancelled	2026-07-10 08:37:56.581247+07	\N	2026-07-10 08:48:40.167706+07	cancelled by user	\N	\N
3660	030afacf	AGV02	go_to	19	cancelled	2026-07-10 08:37:56.582244+07	\N	2026-07-10 08:48:40.167706+07	cancelled by user	\N	\N
3667	9a4288c4	AGV01	go_to	19	cancelled	2026-07-10 08:50:48.308873+07	\N	2026-07-10 08:51:38.171648+07	cancelled by user	\N	\N
3666	8932220c	AGV01	go_to	17	cancelled	2026-07-10 08:50:48.309873+07	2026-07-10 08:50:48.309873+07	2026-07-10 08:51:38.171648+07	force-cancelled by user	\N	\N
3668	b319517f	AGV01	go_to	17	cancelled	2026-07-10 08:50:48.853979+07	\N	2026-07-10 08:51:38.171648+07	cancelled by user	\N	\N
3665	e13e030c	AGV01	go_to	16	cancelled	2026-07-10 08:50:48.308873+07	\N	2026-07-10 08:51:38.171648+07	cancelled by user	\N	\N
3664	304cf782	AGV01	go_charge	\N	cancelled	2026-07-10 08:50:48.307866+07	\N	2026-07-10 08:51:38.171648+07	cancelled by user	\N	\N
3672	aef8c0f5	AGV02	go_to	17	completed	2026-07-10 08:54:28.715987+07	2026-07-10 08:54:28.715987+07	2026-07-10 08:55:14.185129+07	event:continue	\N	\N
3673	07332ba8	AGV02	go_to	17	completed	2026-07-10 08:54:28.7494+07	2026-07-10 08:55:14.186136+07	2026-07-10 08:55:38.046871+07	hook_raised	\N	\N
3690	3cd96411	AGV01	go_to	17	cancelled	2026-07-10 09:57:00.982235+07	\N	2026-07-10 09:57:10.218548+07	cancelled by user	\N	\N
3671	a65eda40	AGV02	go_to	16	completed	2026-07-10 08:54:28.715987+07	2026-07-10 08:55:38.048886+07	2026-07-10 08:56:34.159514+07	event:continue	\N	\N
3686	6f890e09	AGV01	go_charge	\N	cancelled	2026-07-10 09:57:00.585254+07	\N	2026-07-10 09:57:10.218548+07	cancelled by user	\N	\N
3670	9827ab7b	AGV02	go_to	19	completed	2026-07-10 08:54:28.714905+07	2026-07-10 08:56:34.16144+07	2026-07-10 08:57:23.475116+07	off_route	\N	\N
3689	b738f788	AGV01	go_to	17	cancelled	2026-07-10 09:57:00.585254+07	2026-07-10 09:57:00.585254+07	2026-07-10 09:57:10.218548+07	force-cancelled by user	\N	\N
3688	42a441e9	AGV01	go_to	16	cancelled	2026-07-10 09:57:00.585254+07	\N	2026-07-10 09:57:10.218548+07	cancelled by user	\N	\N
3674	c932a012	AGV02	go_to	19	completed	2026-07-10 08:57:23.474121+07	2026-07-10 08:57:23.475116+07	2026-07-10 09:01:25.048358+07	hook_raised	\N	\N
3669	0b9f3fde	AGV02	go_charge	\N	completed	2026-07-10 08:54:28.714905+07	2026-07-10 09:01:25.048358+07	2026-07-10 09:01:59.908262+07	charge_arrived	\N	\N
3687	cbc80cf8	AGV01	go_to	19	cancelled	2026-07-10 09:57:00.585254+07	\N	2026-07-10 09:57:10.218548+07	cancelled by user	\N	\N
3677	623e6aed	AGV01	go_to	17	completed	2026-07-10 09:24:41.464094+07	2026-07-10 09:24:41.464094+07	2026-07-10 09:25:33.306962+07	event:continue	\N	\N
3679	2fbfdd17	AGV01	go_to	17	completed	2026-07-10 09:24:41.945174+07	2026-07-10 09:25:33.307962+07	2026-07-10 09:25:57.164797+07	hook_raised	\N	\N
3678	71d595b3	AGV01	go_to	16	completed	2026-07-10 09:24:41.464094+07	2026-07-10 09:25:57.164797+07	2026-07-10 09:26:48.21575+07	event:continue	\N	\N
3676	f61f02b0	AGV01	go_to	19	cancelled	2026-07-10 09:24:41.463113+07	2026-07-10 09:26:48.21575+07	2026-07-10 09:40:33.883814+07	force-cancelled by user	\N	\N
3675	c356fc60	AGV01	go_charge	\N	cancelled	2026-07-10 09:24:41.463113+07	\N	2026-07-10 09:40:33.883814+07	cancelled by user	\N	\N
3680	2cf35bfd	AGV01	go_charge	\N	completed	2026-07-10 09:40:39.759627+07	2026-07-10 09:40:39.759627+07	2026-07-10 09:41:30.341686+07	off_route	mrebw7yryqgspqpkrj	Sạc Pin
3681	ef8e620b	AGV01	go_charge	14	completed	2026-07-10 09:41:30.340685+07	2026-07-10 09:41:30.342683+07	2026-07-10 09:42:07.134349+07	off_route	mrebw7yryqgspqpkrj	Sạc Pin
3683	7b414422	AGV01	go_to	4	completed	2026-07-10 09:42:07.133332+07	2026-07-10 09:42:07.135336+07	2026-07-10 09:42:24.496478+07	hook_raised	mrebw7yryqgspqpkrj	Sạc Pin
3682	46537ff5	AGV01	go_charge	\N	completed	2026-07-10 09:41:30.561221+07	2026-07-10 09:42:24.497472+07	2026-07-10 09:42:40.536699+07	off_route	mrebw7yryqgspqpkrj	Sạc Pin
3685	8ee309d9	AGV01	go_to	19	cancelled	2026-07-10 09:42:40.535697+07	2026-07-10 09:42:40.537698+07	2026-07-10 09:42:45.246123+07	force-cancelled by user	mrebw7yryqgspqpkrj	Sạc Pin
3684	2351d00a	AGV01	go_charge	\N	cancelled	2026-07-10 09:42:24.515278+07	\N	2026-07-10 09:42:45.246123+07	cancelled by user	mrebw7yryqgspqpkrj	Sạc Pin
3693	01683a73	AGV02	go_to	17	completed	2026-07-10 10:06:26.343263+07	2026-07-10 10:06:26.343263+07	2026-07-10 10:08:34.89119+07	event:continue	\N	\N
3695	5d8318c7	AGV02	go_to	17	completed	2026-07-10 10:06:26.801073+07	2026-07-10 10:08:34.892511+07	2026-07-10 10:08:59.077239+07	hook_raised	\N	\N
3694	9b702ffe	AGV02	go_to	16	completed	2026-07-10 10:06:26.343263+07	2026-07-10 10:08:59.078256+07	2026-07-10 10:09:43.080487+07	event:continue	\N	\N
3691	64648ff2	AGV02	go_to	19	completed	2026-07-10 10:06:26.343263+07	2026-07-10 10:09:43.081469+07	2026-07-10 10:10:12.287092+07	hook_raised	\N	\N
3709	49774ece	AGV01	go_to	17	cancelled	2026-07-10 11:05:10.799126+07	2026-07-10 11:05:10.800132+07	2026-07-10 11:05:19.337228+07	force-cancelled by user	\N	\N
3692	696b3ac7	AGV02	go_charge	\N	completed	2026-07-10 10:06:26.342749+07	2026-07-10 10:10:12.287092+07	2026-07-10 10:10:44.644901+07	charge_arrived	\N	\N
3698	cc46684f	AGV01	go_to	17	completed	2026-07-10 10:25:52.90999+07	2026-07-10 10:25:52.90999+07	2026-07-10 10:27:38.439174+07	event:continue	\N	\N
3700	5c7f3196	AGV01	go_to	17	completed	2026-07-10 10:25:53.359214+07	2026-07-10 10:27:38.439174+07	2026-07-10 10:28:04.327317+07	hook_raised	\N	\N
3705	5611cd30	AGV02	go_to	17	cancelled	2026-07-10 11:04:52.630273+07	\N	2026-07-10 11:05:03.286588+07	cancelled by user	\N	\N
3699	1fa99500	AGV01	go_to	16	completed	2026-07-10 10:25:52.90999+07	2026-07-10 10:28:04.327317+07	2026-07-10 10:29:06.31979+07	event:continue	\N	\N
3703	2b0cdd31	AGV02	go_to	17	cancelled	2026-07-10 11:04:52.114657+07	2026-07-10 11:04:52.11566+07	2026-07-10 11:05:03.285574+07	force-cancelled by user	\N	\N
3697	77f9819b	AGV01	go_to	19	completed	2026-07-10 10:25:52.90999+07	2026-07-10 10:29:06.32079+07	2026-07-10 10:29:35.164108+07	hook_raised	\N	\N
3702	acc04523	AGV02	go_to	19	cancelled	2026-07-10 11:04:52.11366+07	\N	2026-07-10 11:05:03.286588+07	cancelled by user	\N	\N
3701	743ada52	AGV02	go_charge	\N	cancelled	2026-07-10 11:04:52.111667+07	\N	2026-07-10 11:05:03.286588+07	cancelled by user	\N	\N
3704	6c103657	AGV02	go_to	16	cancelled	2026-07-10 11:04:52.114657+07	\N	2026-07-10 11:05:03.286588+07	cancelled by user	\N	\N
3710	479eb84a	AGV01	go_to	17	cancelled	2026-07-10 11:05:10.855785+07	\N	2026-07-10 11:05:19.337228+07	cancelled by user	\N	\N
3708	2b214188	AGV01	go_to	16	cancelled	2026-07-10 11:05:10.799126+07	\N	2026-07-10 11:05:19.337228+07	cancelled by user	\N	\N
3707	4fc04654	AGV01	go_to	19	cancelled	2026-07-10 11:05:10.797129+07	\N	2026-07-10 11:05:19.337228+07	cancelled by user	\N	\N
3706	8f6bdfd2	AGV01	go_charge	\N	cancelled	2026-07-10 11:05:10.797129+07	\N	2026-07-10 11:05:19.337228+07	cancelled by user	\N	\N
3715	2999b4f9	AGV01	go_to	17	completed	2026-07-10 13:25:16.08455+07	2026-07-10 13:26:10.228181+07	2026-07-10 13:26:34.195724+07	hook_raised	\N	\N
3714	5832f6dd	AGV01	go_to	16	completed	2026-07-10 13:25:15.60871+07	2026-07-10 13:26:34.195724+07	2026-07-10 13:27:27.648163+07	event:continue	\N	\N
3718	b8887efd	AGV02	go_to	17	completed	2026-07-10 13:25:36.763409+07	2026-07-10 13:25:36.763409+07	2026-07-10 13:26:49.964898+07	event:continue	\N	\N
3713	ef533481	AGV01	go_to	17	completed	2026-07-10 13:25:15.60871+07	2026-07-10 13:25:15.60871+07	2026-07-10 13:26:10.227178+07	event:continue	\N	\N
3712	fe3227aa	AGV01	go_to	19	completed	2026-07-10 13:25:15.60768+07	2026-07-10 13:27:27.649154+07	2026-07-10 13:27:56.468241+07	hook_raised	\N	\N
3720	b1606d18	AGV02	go_to	17	completed	2026-07-10 13:25:36.793953+07	2026-07-10 13:26:49.965903+07	2026-07-10 13:27:13.794801+07	hook_raised	\N	\N
3722	5c9b1b8b	AGV02	go_charge	\N	cancelled	2026-07-10 13:51:08.122543+07	\N	2026-07-10 13:51:17.500819+07	cancelled by user	\N	\N
3719	3346b64f	AGV02	go_to	16	completed	2026-07-10 13:25:36.762438+07	2026-07-10 13:27:13.795803+07	2026-07-10 13:29:02.607918+07		\N	\N
3711	e1b5d691	AGV01	go_charge	\N	completed	2026-07-10 13:25:15.60768+07	2026-07-10 13:27:56.471235+07	2026-07-10 13:28:33.310075+07	charge_arrived	\N	\N
3721	bfd93234	AGV02	go_to	16	failed	2026-07-10 13:27:13.827935+07	2026-07-10 13:29:02.608918+07	2026-07-10 13:29:02.639275+07	auto-dispatch failed	\N	\N
3717	0b8b6835	AGV02	go_to	19	completed	2026-07-10 13:25:36.762438+07	2026-07-10 13:29:14.408691+07	2026-07-10 13:29:14.411526+07	already_at_dest	\N	\N
3716	fecb030e	AGV02	go_charge	\N	cancelled	2026-07-10 13:25:36.762438+07	2026-07-10 13:29:14.412525+07	2026-07-10 13:31:09.794992+07	force-cancelled by user	\N	\N
3725	cb82520e	AGV02	go_to	17	cancelled	2026-07-10 13:51:08.123535+07	2026-07-10 13:51:08.123535+07	2026-07-10 13:51:17.500187+07	force-cancelled by user	\N	\N
3728	f5bcc5d3	AGV01	go_to	19	cancelled	2026-07-10 13:51:29.076928+07	\N	2026-07-10 13:51:39.639692+07	cancelled by user	\N	\N
3733	0d34a25c	AGV01	go_to	19	completed	2026-07-10 13:54:14.926918+07	2026-07-10 13:58:01.814517+07	2026-07-10 13:58:30.42202+07	hook_raised	\N	\N
3723	81454d6d	AGV02	go_to	19	cancelled	2026-07-10 13:51:08.122543+07	\N	2026-07-10 13:51:17.500819+07	cancelled by user	\N	\N
3724	7aed30bc	AGV02	go_to	16	cancelled	2026-07-10 13:51:08.123535+07	\N	2026-07-10 13:51:17.500819+07	cancelled by user	\N	\N
3726	063853c9	AGV02	go_to	17	cancelled	2026-07-10 13:51:08.485358+07	\N	2026-07-10 13:51:17.500819+07	cancelled by user	\N	\N
3729	ea4e2d9c	AGV01	go_to	16	cancelled	2026-07-10 13:51:29.076928+07	\N	2026-07-10 13:51:39.639692+07	cancelled by user	\N	\N
3727	15d60a8b	AGV01	go_charge	\N	cancelled	2026-07-10 13:51:29.075925+07	\N	2026-07-10 13:51:39.639692+07	cancelled by user	\N	\N
3736	52da7897	AGV01	go_to	17	completed	2026-07-10 13:54:14.981631+07	2026-07-10 13:56:41.483441+07	2026-07-10 13:57:05.148404+07	hook_raised	\N	\N
3740	884d7195	AGV02	go_to	17	completed	2026-07-10 13:54:30.919231+07	2026-07-10 13:54:30.919231+07	2026-07-10 13:57:19.139917+07	event:continue	\N	\N
3735	111459ae	AGV01	go_to	16	completed	2026-07-10 13:54:14.926918+07	2026-07-10 13:57:05.1494+07	2026-07-10 13:58:01.813516+07	event:continue	\N	\N
3742	cb03a065	AGV02	go_to	16	failed	2026-07-10 13:57:49.964954+07	2026-07-10 13:59:36.535077+07	2026-07-10 13:59:36.57047+07	auto-dispatch failed	\N	\N
3738	96605e82	AGV02	go_to	19	cancelled	2026-07-10 13:54:30.919231+07	\N	2026-07-10 14:10:57.138908+07	cancelled by user	\N	\N
3737	980a0049	AGV02	go_charge	\N	cancelled	2026-07-10 13:54:30.918236+07	\N	2026-07-10 14:10:57.138908+07	cancelled by user	\N	\N
3730	1808c9e6	AGV01	go_to	17	cancelled	2026-07-10 13:51:29.077943+07	2026-07-10 13:51:29.077943+07	2026-07-10 13:51:39.639692+07	force-cancelled by user	\N	\N
3734	3102c7c1	AGV01	go_to	17	completed	2026-07-10 13:54:14.926918+07	2026-07-10 13:54:14.926918+07	2026-07-10 13:56:41.482425+07	event:continue	\N	\N
3739	257a873e	AGV02	go_to	16	completed	2026-07-10 13:54:30.919231+07	2026-07-10 13:57:49.955961+07	2026-07-10 13:59:36.534072+07		\N	\N
3731	f8512eea	AGV01	go_to	17	cancelled	2026-07-10 13:51:29.116963+07	\N	2026-07-10 13:51:39.639692+07	cancelled by user	\N	\N
3792	811d81a9	AGV02	go_to	17	cancelled	2026-07-10 16:35:38.752862+07	2026-07-10 16:35:38.752862+07	2026-07-10 16:35:46.390951+07	force-cancelled by user	\N	\N
3741	8d866caa	AGV02	go_to	17	completed	2026-07-10 13:54:30.947533+07	2026-07-10 13:57:19.140916+07	2026-07-10 13:57:49.95396+07	hook_raised	\N	\N
3764	3e71b486	AGV02	go_charge	\N	cancelled	2026-07-10 16:06:02.180994+07	2026-07-10 16:08:44.080351+07	2026-07-10 16:09:16.149692+07	force-cancelled by user	\N	\N
3732	c9d99b82	AGV01	go_charge	\N	completed	2026-07-10 13:54:14.925618+07	2026-07-10 13:58:30.423035+07	2026-07-10 13:59:02.745434+07	charge_arrived	\N	\N
3743	13f4e0cf	AGV02	go_charge	\N	cancelled	2026-07-10 14:56:34.942738+07	2026-07-10 14:56:34.942738+07	2026-07-10 14:56:59.811957+07	force-cancelled by user	mren6hu5mdfvy27gfw	Sạc Pin
3747	5f7d018c	AGV01	go_to	17	completed	2026-07-10 15:42:29.057214+07	2026-07-10 15:42:29.057214+07	2026-07-10 15:43:17.036971+07	event:continue	\N	\N
3748	79a5484b	AGV01	go_to	17	completed	2026-07-10 15:42:29.473249+07	2026-07-10 15:43:17.038918+07	2026-07-10 15:43:41.839614+07	hook_raised	\N	\N
3746	ee9fbd88	AGV01	go_to	16	completed	2026-07-10 15:42:29.056216+07	2026-07-10 15:43:41.841928+07	2026-07-10 15:44:40.958338+07	event:continue	\N	\N
3745	c7a0f9cb	AGV01	go_to	19	completed	2026-07-10 15:42:29.056216+07	2026-07-10 15:44:40.959336+07	2026-07-10 15:45:09.601264+07	hook_raised	\N	\N
3744	f5e1c931	AGV01	go_charge	\N	completed	2026-07-10 15:42:29.056216+07	2026-07-10 15:45:09.603269+07	2026-07-10 15:48:11.864104+07	charge_arrived	\N	\N
3753	da666c03	AGV01	go_to	17	cancelled	2026-07-10 15:51:44.158441+07	\N	2026-07-10 15:53:19.854972+07	cancelled by user	\N	\N
3752	9c9fc17a	AGV01	go_to	17	cancelled	2026-07-10 15:51:43.677105+07	2026-07-10 15:51:43.677105+07	2026-07-10 15:53:19.854972+07	force-cancelled by user	\N	\N
3751	a19373cf	AGV01	go_to	16	cancelled	2026-07-10 15:51:43.676105+07	\N	2026-07-10 15:53:19.854972+07	cancelled by user	\N	\N
3749	1a40072c	AGV01	go_charge	\N	cancelled	2026-07-10 15:51:43.675109+07	\N	2026-07-10 15:53:19.854972+07	cancelled by user	\N	\N
3750	eaa61ee8	AGV01	go_to	19	cancelled	2026-07-10 15:51:43.676105+07	\N	2026-07-10 15:53:19.854972+07	cancelled by user	\N	\N
3756	585da986	AGV01	go_to	17	completed	2026-07-10 15:54:05.85408+07	2026-07-10 15:54:05.85408+07	2026-07-10 15:54:56.194154+07	event:continue	\N	\N
3773	2c02f5e5	AGV01	go_to	17	cancelled	2026-07-10 16:12:46.940409+07	\N	2026-07-10 16:12:59.73445+07	cancelled by user	\N	\N
3758	2b2a8b74	AGV01	go_to	17	completed	2026-07-10 15:54:05.889317+07	2026-07-10 15:54:56.194154+07	2026-07-10 15:55:19.909181+07	hook_raised	\N	\N
3771	6014591f	AGV01	go_to	19	cancelled	2026-07-10 16:12:46.636765+07	\N	2026-07-10 16:12:59.73445+07	cancelled by user	\N	\N
3757	2db2d341	AGV01	go_to	16	completed	2026-07-10 15:54:05.85408+07	2026-07-10 15:55:19.910182+07	2026-07-10 15:56:56.052771+07	event:continue	\N	\N
3769	535cf78f	AGV01	go_charge	\N	cancelled	2026-07-10 16:12:46.636765+07	\N	2026-07-10 16:12:59.73445+07	cancelled by user	\N	\N
3755	6ef8d6a1	AGV01	go_to	19	completed	2026-07-10 15:54:05.85408+07	2026-07-10 15:56:56.052771+07	2026-07-10 15:57:38.499577+07	hook_raised	\N	\N
3772	828d6bbb	AGV01	go_to	17	cancelled	2026-07-10 16:12:46.637762+07	2026-07-10 16:12:46.637762+07	2026-07-10 16:12:59.73445+07	force-cancelled by user	\N	\N
3754	f052e1de	AGV01	go_charge	\N	completed	2026-07-10 15:54:05.853074+07	2026-07-10 15:57:38.501004+07	2026-07-10 15:58:14.766474+07	charge_arrived	\N	\N
3770	b4a42033	AGV01	go_to	16	cancelled	2026-07-10 16:12:46.636765+07	\N	2026-07-10 16:12:59.73445+07	cancelled by user	\N	\N
3762	ec3291e3	AGV02	go_to	16	cancelled	2026-07-10 16:04:58.906346+07	\N	2026-07-10 16:05:08.384759+07	cancelled by user	\N	\N
3761	d56f0291	AGV02	go_to	17	cancelled	2026-07-10 16:04:58.912802+07	2026-07-10 16:04:58.930308+07	2026-07-10 16:05:08.384759+07	force-cancelled by user	\N	\N
3763	146e5032	AGV02	go_to	17	cancelled	2026-07-10 16:04:59.496791+07	\N	2026-07-10 16:05:08.384759+07	cancelled by user	\N	\N
3759	2fb6c3ac	AGV02	go_charge	\N	cancelled	2026-07-10 16:04:58.901231+07	\N	2026-07-10 16:05:08.384759+07	cancelled by user	\N	\N
3760	577c35c4	AGV02	go_to	19	cancelled	2026-07-10 16:04:58.904233+07	\N	2026-07-10 16:05:08.384759+07	cancelled by user	\N	\N
3766	458dbbd2	AGV02	go_to	17	completed	2026-07-10 16:06:02.183+07	2026-07-10 16:06:02.183+07	2026-07-10 16:06:48.591146+07	event:continue	\N	\N
3768	85687dfd	AGV02	go_to	17	completed	2026-07-10 16:06:02.222113+07	2026-07-10 16:06:48.592145+07	2026-07-10 16:07:13.166476+07	hook_raised	\N	\N
3767	4ef4c149	AGV02	go_to	16	completed	2026-07-10 16:06:02.182047+07	2026-07-10 16:07:13.166476+07	2026-07-10 16:08:00.197212+07	event:continue	\N	\N
3765	f0a088bb	AGV02	go_to	19	completed	2026-07-10 16:06:02.182047+07	2026-07-10 16:08:00.197212+07	2026-07-10 16:08:44.07783+07	hook_raised	\N	\N
3793	ae3a52fc	AGV02	go_to	17	cancelled	2026-07-10 16:35:39.080996+07	\N	2026-07-10 16:35:46.390951+07	cancelled by user	\N	\N
3777	8133ea49	AGV01	go_to	17	completed	2026-07-10 16:13:31.736668+07	2026-07-10 16:13:31.736668+07	2026-07-10 16:14:21.275478+07	event:continue	\N	\N
3778	3101d4af	AGV01	go_to	17	completed	2026-07-10 16:13:31.767638+07	2026-07-10 16:14:21.27648+07	2026-07-10 16:14:45.282652+07	hook_raised	\N	\N
3787	1be2cff0	AGV02	go_to	17	completed	2026-07-10 16:24:35.299555+07	2026-07-10 16:24:35.299555+07	2026-07-10 16:25:20.23634+07	event:continue	\N	\N
3776	f279b99b	AGV01	go_to	16	completed	2026-07-10 16:13:31.736668+07	2026-07-10 16:14:45.284673+07	2026-07-10 16:15:34.870002+07	event:continue	\N	\N
3791	a8aa5ac2	AGV02	go_to	16	cancelled	2026-07-10 16:35:38.752862+07	\N	2026-07-10 16:35:46.390951+07	cancelled by user	\N	\N
3775	09b41713	AGV01	go_to	19	completed	2026-07-10 16:13:31.735641+07	2026-07-10 16:15:34.870002+07	2026-07-10 16:16:05.691845+07	hook_raised	\N	\N
3788	e2b624ea	AGV02	go_to	17	completed	2026-07-10 16:24:35.690741+07	2026-07-10 16:25:20.23734+07	2026-07-10 16:25:44.219778+07	hook_raised	\N	\N
3782	8b592f0d	AGV02	go_to	17	cancelled	2026-07-10 16:16:33.309543+07	2026-07-10 16:16:33.309543+07	2026-07-10 16:16:39.520049+07	force-cancelled by user	\N	\N
3783	7315afc2	AGV02	go_to	17	cancelled	2026-07-10 16:16:33.368751+07	\N	2026-07-10 16:16:39.521017+07	cancelled by user	\N	\N
3781	48f77e01	AGV02	go_to	16	cancelled	2026-07-10 16:16:33.309543+07	\N	2026-07-10 16:16:39.521017+07	cancelled by user	\N	\N
3780	ee94b903	AGV02	go_to	19	cancelled	2026-07-10 16:16:33.308601+07	\N	2026-07-10 16:16:39.521017+07	cancelled by user	\N	\N
3779	727339b7	AGV02	go_charge	\N	cancelled	2026-07-10 16:16:33.308601+07	\N	2026-07-10 16:16:39.521017+07	cancelled by user	\N	\N
3774	7536e80e	AGV01	go_charge	\N	completed	2026-07-10 16:13:31.735641+07	2026-07-10 16:16:05.692844+07	2026-07-10 16:16:39.974369+07	charge_arrived	\N	\N
3786	c71d00e1	AGV02	go_to	16	completed	2026-07-10 16:24:35.299555+07	2026-07-10 16:25:44.220794+07	2026-07-10 16:26:30.14958+07	event:continue	\N	\N
3789	17a8a509	AGV02	go_charge	\N	cancelled	2026-07-10 16:35:38.752862+07	\N	2026-07-10 16:35:46.390951+07	cancelled by user	\N	\N
3785	21c2891f	AGV02	go_to	19	completed	2026-07-10 16:24:35.299555+07	2026-07-10 16:26:30.150518+07	2026-07-10 16:27:01.737157+07	hook_raised	\N	\N
3784	b60a4cfe	AGV02	go_charge	\N	completed	2026-07-10 16:24:35.298552+07	2026-07-10 16:27:01.738154+07	2026-07-10 16:27:35.934936+07	charge_arrived	\N	\N
3790	9b1fe755	AGV02	go_to	19	cancelled	2026-07-10 16:35:38.752862+07	\N	2026-07-10 16:35:46.390951+07	cancelled by user	\N	\N
3797	745bf3a5	AGV02	go_to	17	completed	2026-07-10 16:36:41.58288+07	2026-07-10 16:36:41.58288+07	2026-07-10 16:37:33.541887+07	event:continue	\N	\N
3794	a589a020	AGV02	go_charge	\N	completed	2026-07-10 16:36:41.581814+07	2026-07-10 16:39:04.359444+07	2026-07-10 16:39:44.769121+07	charge_arrived	\N	\N
3798	ba137cfb	AGV02	go_to	17	completed	2026-07-10 16:36:41.621282+07	2026-07-10 16:37:33.54289+07	2026-07-10 16:37:57.428171+07	hook_raised	\N	\N
3795	8cfea728	AGV02	go_to	19	completed	2026-07-10 16:36:41.58288+07	2026-07-10 16:38:32.820148+07	2026-07-10 16:39:04.358088+07	hook_raised	\N	\N
3796	e8bbe42f	AGV02	go_to	16	completed	2026-07-10 16:36:41.58288+07	2026-07-10 16:37:57.428171+07	2026-07-10 16:38:32.819148+07	event:continue	\N	\N
3800	616642bb	AGV02	go_to	16	cancelled	2026-07-10 16:44:23.220065+07	\N	2026-07-10 16:44:31.670643+07	cancelled by user	\N	\N
3803	df3646b9	AGV02	go_to	17	cancelled	2026-07-10 16:44:23.70319+07	\N	2026-07-10 16:44:31.670643+07	cancelled by user	\N	\N
3802	9f85f9c7	AGV02	go_to	17	cancelled	2026-07-10 16:44:23.220065+07	2026-07-10 16:44:23.220065+07	2026-07-10 16:44:31.670643+07	force-cancelled by user	\N	\N
3799	9248cd83	AGV02	go_charge	\N	cancelled	2026-07-10 16:44:23.219066+07	\N	2026-07-10 16:44:31.670643+07	cancelled by user	\N	\N
3801	7ba6ae7d	AGV02	go_to	19	cancelled	2026-07-10 16:44:23.219066+07	\N	2026-07-10 16:44:31.670643+07	cancelled by user	\N	\N
3806	dfcc4105	AGV02	go_to	17	completed	2026-07-10 17:00:41.371998+07	2026-07-10 17:00:41.372998+07	2026-07-10 17:01:25.664432+07	event:continue	\N	\N
3808	0e2ec57f	AGV02	go_to	17	completed	2026-07-10 17:00:41.936785+07	2026-07-10 17:01:25.664432+07	2026-07-10 17:02:05.673595+07	hook_raised	\N	\N
3807	da64f88c	AGV02	go_to	16	completed	2026-07-10 17:00:41.371998+07	2026-07-10 17:02:05.676595+07	2026-07-10 17:02:58.456625+07	event:continue	\N	\N
3810	9a06212c	AGV01	go_to	19	completed	2026-07-10 17:00:55.183969+07	2026-07-10 17:04:35.799229+07	2026-07-10 17:05:08.810845+07	hook_raised	\N	\N
3818	3f72f3da	AGV02	go_to	17	cancelled	2026-07-10 17:04:16.007253+07	\N	2026-07-10 17:06:05.67835+07	cancelled by user	\N	\N
3809	39e18533	AGV01	go_charge	\N	cancelled	2026-07-10 17:00:55.183969+07	2026-07-10 17:05:08.811941+07	2026-07-10 17:07:08.124879+07	force-cancelled by user	\N	\N
3821	fb90c6f2	AGV01	go_to	17	failed	2026-07-10 17:07:22.727628+07	2026-07-10 17:07:22.727628+07	2026-07-10 17:07:22.791387+07	auto-dispatch failed	\N	\N
3827	e3107835	AGV02	go_to	17	cancelled	2026-07-10 17:07:45.539108+07	\N	2026-07-10 17:08:10.507319+07	cancelled by user	\N	\N
3824	4460e066	AGV02	go_to	19	cancelled	2026-07-10 17:07:45.490138+07	\N	2026-07-10 17:08:10.507319+07	cancelled by user	\N	\N
3830	eb4a4cf2	AGV02	go_to	16	queued	2026-07-10 17:08:44.85526+07	\N	\N	\N	\N	\N
3811	a3ece76c	AGV01	go_to	17	completed	2026-07-10 17:00:55.187085+07	2026-07-10 17:00:55.187085+07	2026-07-10 17:02:27.521621+07	event:continue	\N	\N
3812	a2a1f5d9	AGV01	go_to	16	completed	2026-07-10 17:00:55.184969+07	2026-07-10 17:03:06.405682+07	2026-07-10 17:04:35.797222+07	event:continue	\N	\N
3817	3cb4cd8a	AGV02	go_to	17	cancelled	2026-07-10 17:04:15.978245+07	2026-07-10 17:04:15.978245+07	2026-07-10 17:06:05.677349+07	force-cancelled by user	\N	\N
3814	d1940431	AGV02	go_charge	\N	cancelled	2026-07-10 17:04:15.977238+07	\N	2026-07-10 17:06:05.67835+07	cancelled by user	\N	\N
3822	5538c200	AGV01	go_to	19	cancelled	2026-07-10 17:07:22.726711+07	\N	2026-07-10 17:07:34.524591+07	cancelled by user	\N	\N
3819	592f3668	AGV01	go_charge	\N	cancelled	2026-07-10 17:07:22.726711+07	\N	2026-07-10 17:07:34.524591+07	cancelled by user	\N	\N
3823	11c8c960	AGV02	go_charge	\N	cancelled	2026-07-10 17:07:45.490138+07	\N	2026-07-10 17:08:10.507319+07	cancelled by user	\N	\N
3829	53fe696f	AGV02	go_to	19	queued	2026-07-10 17:08:44.854202+07	\N	\N	\N	\N	\N
3832	728cdbe0	AGV02	go_to	17	queued	2026-07-10 17:08:44.884533+07	\N	\N	\N	\N	\N
3813	287a7772	AGV01	go_to	17	completed	2026-07-10 17:00:55.2413+07	2026-07-10 17:02:27.522666+07	2026-07-10 17:03:06.403675+07	hook_raised	\N	\N
3805	fc1dfaf2	AGV02	go_to	19	completed	2026-07-10 17:00:41.371998+07	2026-07-10 17:02:58.457861+07	2026-07-10 17:03:35.634817+07	hook_raised	\N	\N
3816	6d49e533	AGV02	go_to	16	cancelled	2026-07-10 17:04:15.977238+07	\N	2026-07-10 17:06:05.67835+07	cancelled by user	\N	\N
3826	6c244d34	AGV02	go_to	16	cancelled	2026-07-10 17:07:45.49118+07	\N	2026-07-10 17:08:10.507319+07	cancelled by user	\N	\N
3828	dfcdefcc	AGV02	go_charge	\N	queued	2026-07-10 17:08:44.854202+07	\N	\N	\N	\N	\N
3804	11c26a53	AGV02	go_charge	\N	completed	2026-07-10 17:00:41.370997+07	2026-07-10 17:03:35.637099+07	2026-07-10 17:04:05.891861+07	charge_arrived	\N	\N
3815	b6cbbc42	AGV02	go_to	19	cancelled	2026-07-10 17:04:15.977238+07	\N	2026-07-10 17:06:05.67835+07	cancelled by user	\N	\N
3820	f4a9d4d3	AGV01	go_to	16	cancelled	2026-07-10 17:07:22.726711+07	\N	2026-07-10 17:07:34.524591+07	cancelled by user	\N	\N
3825	1726308c	AGV02	go_to	17	cancelled	2026-07-10 17:07:45.49118+07	2026-07-10 17:07:45.49118+07	2026-07-10 17:08:10.507319+07	force-cancelled by user	\N	\N
3831	05767615	AGV02	go_to	17	running	2026-07-10 17:08:44.85526+07	\N	\N	\N	\N	\N
3860	7b9bb882	AGV01	go_charge	\N	cancelled	2026-07-14 14:39:08.689255+07	\N	2026-07-14 14:39:54.531664+07	cancelled by user	mrkcb74o72sxhod7xrw	Sạc Pin
3837	f7461a5b	AGV01	go_to	17	cancelled	2026-07-11 08:53:06.810039+07	\N	2026-07-11 08:53:23.040256+07	cancelled by user	\N	\N
3836	1dad9829	AGV01	go_to	17	cancelled	2026-07-11 08:53:06.090415+07	2026-07-11 08:53:06.092422+07	2026-07-11 08:53:23.040256+07	force-cancelled by user	\N	\N
3835	b8708bb9	AGV01	go_to	16	cancelled	2026-07-11 08:53:06.090415+07	\N	2026-07-11 08:53:23.040256+07	cancelled by user	\N	\N
3834	45042503	AGV01	go_to	19	cancelled	2026-07-11 08:53:06.089421+07	\N	2026-07-11 08:53:23.040256+07	cancelled by user	\N	\N
3833	f0a40a41	AGV01	go_charge	\N	cancelled	2026-07-11 08:53:06.088421+07	\N	2026-07-11 08:53:23.040256+07	cancelled by user	\N	\N
3859	aead7521	AGV01	go_charge	10	cancelled	2026-07-14 14:39:08.469248+07	2026-07-14 14:39:08.472611+07	2026-07-14 14:39:54.530655+07	force-cancelled by user	mrkcb74o72sxhod7xrw	Sạc Pin
3842	f700406f	AGV01	go_to	17	cancelled	2026-07-11 08:54:46.155972+07	\N	2026-07-11 08:55:39.287877+07	cancelled by user	\N	\N
3839	b4ce9fbb	AGV01	go_to	19	cancelled	2026-07-11 08:54:46.082273+07	\N	2026-07-11 08:55:39.287877+07	cancelled by user	\N	\N
3840	14fe3082	AGV01	go_to	16	cancelled	2026-07-11 08:54:46.083286+07	\N	2026-07-11 08:55:39.287877+07	cancelled by user	\N	\N
3838	35b9bf3b	AGV01	go_charge	\N	cancelled	2026-07-11 08:54:46.081283+07	\N	2026-07-11 08:55:39.287877+07	cancelled by user	\N	\N
3841	ba96f467	AGV01	go_to	17	cancelled	2026-07-11 08:54:46.083286+07	2026-07-11 08:54:46.084278+07	2026-07-11 08:55:39.287877+07	force-cancelled by user	\N	\N
3846	f5378bf6	AGV01	go_to	17	completed	2026-07-11 08:57:19.980685+07	2026-07-11 08:57:19.980685+07	2026-07-11 08:58:04.092527+07	event:continue	\N	\N
3861	6b376607	AGV01	go_charge	\N	completed	2026-07-14 14:40:17.318549+07	2026-07-14 14:40:17.318549+07	2026-07-14 14:40:24.215607+07		mrkccy8gqhut1jtlpgm	Sạc Pin
3847	6da91991	AGV01	go_to	17	completed	2026-07-11 08:57:20.012947+07	2026-07-11 08:58:04.094316+07	2026-07-11 08:58:27.810648+07	hook_raised	\N	\N
3871	f5e1a191	AGV01	go_to	20	completed	2026-07-14 14:56:18.121599+07	2026-07-14 14:56:18.122599+07	2026-07-14 14:58:02.617854+07	off_route	\N	hmi_station_trigger
3845	7ae31588	AGV01	go_to	16	completed	2026-07-11 08:57:19.979688+07	2026-07-11 08:58:27.811754+07	2026-07-11 08:59:06.637588+07	event:continue	\N	\N
3844	8f71597e	AGV01	go_to	19	completed	2026-07-11 08:57:19.979688+07	2026-07-11 08:59:06.638557+07	2026-07-11 08:59:35.293609+07	hook_raised	\N	\N
3862	9413d6aa	AGV01	go_charge	\N	completed	2026-07-14 14:40:17.342779+07	2026-07-14 14:40:24.215607+07	2026-07-14 14:44:30.033131+07	off_route	mrkccy8gqhut1jtlpgm	Sạc Pin
3843	0cf80854	AGV01	go_charge	\N	completed	2026-07-11 08:57:19.979688+07	2026-07-11 08:59:35.294116+07	2026-07-11 09:00:15.783477+07	charge_arrived	\N	\N
3852	1abf3852	AGV02	go_to	17	cancelled	2026-07-11 09:00:29.284779+07	\N	2026-07-11 09:00:44.411032+07	cancelled by user	\N	\N
3849	cac94baa	AGV02	go_to	16	cancelled	2026-07-11 09:00:29.229255+07	\N	2026-07-11 09:00:44.411032+07	cancelled by user	\N	\N
3848	7037cf3b	AGV02	go_charge	\N	cancelled	2026-07-11 09:00:29.227259+07	\N	2026-07-11 09:00:44.411032+07	cancelled by user	\N	\N
3850	5e16dde7	AGV02	go_to	17	cancelled	2026-07-11 09:00:29.231256+07	2026-07-11 09:00:29.231256+07	2026-07-11 09:00:44.410015+07	force-cancelled by user	\N	\N
3851	0ad06786	AGV02	go_to	19	cancelled	2026-07-11 09:00:29.228253+07	\N	2026-07-11 09:00:44.411032+07	cancelled by user	\N	\N
3854	e7d528f4	AGV02	go_to	19	cancelled	2026-07-11 09:03:30.94636+07	\N	2026-07-11 09:04:04.968272+07	cancelled by user	\N	\N
3855	cbebf5e6	AGV02	go_to	16	cancelled	2026-07-11 09:03:30.94636+07	\N	2026-07-11 09:04:04.968272+07	cancelled by user	\N	\N
3853	5f8c1e28	AGV02	go_charge	\N	cancelled	2026-07-11 09:03:30.945364+07	\N	2026-07-11 09:04:04.968272+07	cancelled by user	\N	\N
3856	578c892d	AGV02	go_to	17	cancelled	2026-07-11 09:03:30.94636+07	2026-07-11 09:03:30.94636+07	2026-07-11 09:04:04.968272+07	force-cancelled by user	\N	\N
3857	6bf4ba3b	AGV02	go_to	17	cancelled	2026-07-11 09:03:30.971356+07	\N	2026-07-11 09:04:04.968272+07	cancelled by user	\N	\N
3858	ba02415d	AGV01	go_charge	\N	completed	2026-07-14 14:38:55.598348+07	2026-07-14 14:38:55.598348+07	2026-07-14 14:39:08.470301+07	off_route	mrkcb74o72sxhod7xrw	Sạc Pin
3878	0f2a030e	AGV01	go_charge	\N	cancelled	2026-07-14 15:31:01.71844+07	2026-07-14 15:31:01.71844+07	2026-07-14 15:37:21.739266+07	force-cancelled by user	\N	hmi_station_trigger
3863	83eb0866	AGV01	go_charge	10	completed	2026-07-14 14:44:30.031968+07	2026-07-14 14:44:30.034385+07	2026-07-14 14:44:40.473057+07	off_route	mrkccy8gqhut1jtlpgm	Sạc Pin
3864	e21b3e9f	AGV01	go_charge	10	completed	2026-07-14 14:44:40.472058+07	2026-07-14 14:44:40.473057+07	2026-07-14 14:46:12.542453+07		mrkccy8gqhut1jtlpgm	Sạc Pin
3865	047872ee	AGV01	go_charge	\N	completed	2026-07-14 14:44:40.492972+07	2026-07-14 14:46:12.543452+07	2026-07-14 14:48:04.955144+07	off_route	mrkccy8gqhut1jtlpgm	Sạc Pin
3866	bec7a3c2	AGV01	go_charge	10	cancelled	2026-07-14 14:48:04.95415+07	2026-07-14 14:48:04.955144+07	2026-07-14 14:48:47.464207+07	force-cancelled by user	mrkccy8gqhut1jtlpgm	Sạc Pin
3867	7f653628	AGV01	go_charge	\N	completed	2026-07-14 14:55:07.54796+07	2026-07-14 14:55:07.54796+07	2026-07-14 14:55:15.013164+07	off_route	\N	hmi_station_trigger
3872	8f355f86	AGV01	go_to	20	completed	2026-07-14 14:58:02.616847+07	2026-07-14 14:58:02.619841+07	2026-07-14 15:04:07.450466+07	off_route	\N	hmi_station_trigger
3868	2e958ba8	AGV01	go_charge	10	completed	2026-07-14 14:55:15.01216+07	2026-07-14 14:55:15.014163+07	2026-07-14 14:55:45.643071+07	off_route	\N	hmi_station_trigger
3870	c2d33a05	AGV01	go_charge	\N	queued	2026-07-14 14:55:45.650067+07	\N	\N	\N	\N	hmi_station_trigger
3869	24ba440a	AGV01	go_charge	10	completed	2026-07-14 14:55:45.643071+07	2026-07-14 14:55:45.644172+07	2026-07-14 14:56:18.121599+07	off_route	\N	hmi_station_trigger
3873	4642447e	AGV01	go_to	20	completed	2026-07-14 15:04:07.449376+07	2026-07-14 15:04:07.451485+07	2026-07-14 15:04:18.640261+07	off_route	\N	hmi_station_trigger
3874	8067fa5a	AGV01	go_to	20	failed	2026-07-14 15:04:18.639263+07	2026-07-14 15:04:18.640261+07	2026-07-14 15:04:18.686975+07	auto-dispatch failed	\N	hmi_station_trigger
3875	7ce5798a	AGV01	go_charge	\N	running	2026-07-14 15:06:10.819747+07	\N	\N	\N	\N	hmi_station_trigger
3876	47847247	AGV01	go_charge	\N	completed	2026-07-14 15:07:46.604162+07	2026-07-14 15:07:46.604162+07	2026-07-14 15:08:02.559759+07	off_route	\N	hmi_station_trigger
3877	e5ca2786	AGV01	go_charge	10	running	2026-07-14 15:08:02.559759+07	2026-07-14 15:08:02.561196+07	\N		\N	hmi_station_trigger
3879	ea6281f6	AGV01	go_charge	\N	completed	2026-07-14 16:35:05.15786+07	2026-07-14 16:35:05.15786+07	2026-07-14 16:35:43.182136+07	off_route	\N	hmi_station_trigger
3880	28ae1408	AGV01	go_charge	10	running	2026-07-14 16:35:43.182136+07	2026-07-14 16:35:43.182136+07	\N		\N	hmi_station_trigger
3881	37461d64	AGV01	go_charge	\N	cancelled	2026-07-15 10:18:08.768833+07	2026-07-15 10:18:08.768833+07	2026-07-15 10:19:41.14305+07	force-cancelled by user	\N	hmi_station_trigger
3882	1783d543	AGV01	go_charge	\N	cancelled	2026-07-15 10:19:36.484033+07	\N	2026-07-15 10:19:41.14305+07	cancelled by user	\N	hmi_station_trigger
3883	8d2dab64	AGV01	go_charge	\N	cancelled	2026-07-15 10:19:38.426502+07	\N	2026-07-15 10:19:41.14305+07	cancelled by user	\N	hmi_station_trigger
3884	5589edc7	AGV01	go_charge	\N	cancelled	2026-07-15 10:19:38.863976+07	\N	2026-07-15 10:19:41.14305+07	cancelled by user	\N	hmi_station_trigger
3886	97072d50	AGV01	go_charge	\N	cancelled	2026-07-15 10:19:39.428075+07	\N	2026-07-15 10:19:41.14305+07	cancelled by user	\N	hmi_station_trigger
3885	5d6e4929	AGV01	go_charge	\N	cancelled	2026-07-15 10:19:39.196049+07	\N	2026-07-15 10:19:41.14305+07	cancelled by user	\N	hmi_station_trigger
3887	ab33a09f	AGV01	go_charge	\N	completed	2026-07-15 10:19:59.626455+07	2026-07-15 10:19:59.625305+07	2026-07-15 10:20:21.581435+07	off_route	\N	hmi_station_trigger
3889	19e6f980	AGV01	go_charge	\N	cancelled	2026-07-15 10:20:21.619472+07	\N	2026-07-15 10:20:35.189314+07	cancelled by user	\N	hmi_station_trigger
3888	fdfa6602	AGV01	go_charge	10	cancelled	2026-07-15 10:20:21.579429+07	2026-07-15 10:20:21.582427+07	2026-07-15 10:20:35.188317+07	force-cancelled by user	\N	hmi_station_trigger
3890	d3b2ec2d	AGV01	go_to	108	failed	2026-07-15 10:31:20.380472+07	2026-07-15 10:31:20.380472+07	2026-07-15 10:31:20.402462+07	dispatch failed	mrliwnfxi5jarwdnre	A06
3891	4161900a	AGV01	go_charge	\N	cancelled	2026-07-15 10:31:20.414459+07	2026-07-15 10:31:20.414459+07	2026-07-15 10:32:09.926079+07	force-cancelled by user	mrliwnfxi5jarwdnre	A06
3892	b15a8510	AGV01	go_to	108	failed	2026-07-15 10:33:17.814419+07	2026-07-15 10:33:17.814419+07	2026-07-15 10:33:17.842422+07	dispatch failed	mrliz6294zswi2dlo0k	A06
3893	31a1e099	AGV01	go_charge	\N	cancelled	2026-07-15 10:33:17.852425+07	2026-07-15 10:33:17.852425+07	2026-07-15 10:33:25.427142+07	force-cancelled by user	mrliz6294zswi2dlo0k	A06
3894	054a0621	AGV01	go_to	108	failed	2026-07-15 10:34:04.069844+07	2026-07-15 10:34:04.069844+07	2026-07-15 10:34:04.328457+07	dispatch failed	mrlj05pyrj8q9rou43	A06
3895	af56696a	AGV01	go_charge	\N	cancelled	2026-07-15 10:34:04.342151+07	2026-07-15 10:34:04.342151+07	2026-07-15 10:39:26.806433+07	force-cancelled by user	mrlj05pyrj8q9rou43	A06
3896	fb48ee59	AGV01	go_to	108	cancelled	2026-07-15 10:39:46.239186+07	2026-07-15 10:39:46.239186+07	2026-07-15 10:43:39.967531+07	force-cancelled by user	mrlj7hrjaaokb0ohpa6	A06
3897	b2c97391	AGV01	go_to	108	cancelled	2026-07-15 10:39:46.432516+07	\N	2026-07-15 10:43:39.968532+07	cancelled by user	mrlj7hrjaaokb0ohpa6	A06
3898	d0a24940	AGV01	go_charge	\N	cancelled	2026-07-15 10:39:46.436154+07	\N	2026-07-15 10:43:39.968532+07	cancelled by user	mrlj7hrjaaokb0ohpa6	A06
3899	782a74b8	AGV01	go_to	108	cancelled	2026-07-15 10:45:30.314183+07	2026-07-15 10:45:30.314183+07	2026-07-15 10:49:08.060322+07	force-cancelled by user	mrljev9kzwxssxi1iq	A06
3900	90692979	AGV01	go_charge	\N	cancelled	2026-07-15 10:45:30.388927+07	\N	2026-07-15 10:49:08.061361+07	cancelled by user	mrljev9kzwxssxi1iq	A06
3901	e5efdcd6	AGV01	go_to	108	cancelled	2026-07-15 10:49:30.600715+07	2026-07-15 10:49:30.600715+07	2026-07-15 10:50:21.711276+07	force-cancelled by user	mrljk0mt8rguhyq0lo7	A06
3902	86f3264a	AGV01	go_charge	\N	cancelled	2026-07-15 10:49:30.859704+07	\N	2026-07-15 10:50:21.712272+07	cancelled by user	mrljk0mt8rguhyq0lo7	A06
3903	6c0a5671	AGV01	go_to	108	running	2026-07-15 11:00:50.904853+07	\N	\N	\N	mrljylkio21p2rcvszl	A06
3904	9a6465ab	AGV01	go_charge	\N	queued	2026-07-15 11:00:50.920853+07	\N	\N	\N	mrljylkio21p2rcvszl	A06
3905	ead48dc4	AGV01	go_to	108	cancelled	2026-07-15 11:05:50.477556+07	2026-07-15 11:05:50.477556+07	2026-07-15 11:06:25.057417+07	force-cancelled by user	mrlk50q5msod56jxja	A06
3906	2bca9188	AGV01	go_charge	\N	cancelled	2026-07-15 11:05:50.64492+07	\N	2026-07-15 11:06:25.057417+07	cancelled by user	mrlk50q5msod56jxja	A06
3908	0bd1b457	AGV01	go_charge	\N	cancelled	2026-07-15 11:18:00.038578+07	\N	2026-07-15 11:18:37.628226+07	cancelled by user	mrlkknmgvmom89ixz8j	A06
3907	74055d2f	AGV01	go_to	108	cancelled	2026-07-15 11:17:59.96982+07	2026-07-15 11:17:59.96982+07	2026-07-15 11:18:37.625745+07	force-cancelled by user	mrlkknmgvmom89ixz8j	A06
3910	e8396106	AGV01	go_charge	\N	cancelled	2026-07-15 11:32:04.0307+07	\N	2026-07-15 11:32:58.613722+07	cancelled by user	mrll2qsgtpx0ylke0dk	A06
3909	50cd3886	AGV01	go_to	108	cancelled	2026-07-15 11:32:03.869409+07	2026-07-15 11:32:03.869409+07	2026-07-15 11:32:58.613722+07	force-cancelled by user	mrll2qsgtpx0ylke0dk	A06
3911	e5c9ccd1	AGV01	go_to	108	completed	2026-07-15 14:46:54.84252+07	2026-07-15 14:46:54.84252+07	2026-07-15 14:50:42.180258+07	event:continue	mrls1bkeegsg2x19sij	A06
3918	22829199	AGV01	go_to	104	completed	2026-07-15 15:14:16.624018+07	2026-07-15 15:14:16.624018+07	2026-07-15 15:15:22.763157+07	off_route	mrlt0ie6638st1487md	A06
3912	cf1f1dfd	AGV01	go_charge	\N	cancelled	2026-07-15 14:46:55.04975+07	2026-07-15 14:50:42.181272+07	2026-07-15 14:59:56.049758+07	force-cancelled by user	mrls1bkeegsg2x19sij	A06
3913	6bd5d58e	AGV01	go_to	104	completed	2026-07-15 15:00:07.648422+07	2026-07-15 15:00:07.648422+07	2026-07-15 15:01:16.3035+07	off_route	mrlsibbwhnxihh0n0ho	A06
3927	fa1eb16b	AGV01	go_to	81	cancelled	2026-07-15 15:34:45.840906+07	\N	2026-07-15 15:44:43.297042+07	cancelled by user	\N	\N
3915	f9a3b545	AGV01	go_charge	\N	cancelled	2026-07-15 15:00:07.657373+07	\N	2026-07-15 15:03:08.953275+07	cancelled by user	mrlsibbwhnxihh0n0ho	A06
3914	910b3893	AGV01	go_to	104	cancelled	2026-07-15 15:00:07.657373+07	\N	2026-07-15 15:03:08.953275+07	cancelled by user	mrlsibbwhnxihh0n0ho	A06
3916	3957e2ba	AGV01	go_to	81	cancelled	2026-07-15 15:01:16.302484+07	2026-07-15 15:01:16.3035+07	2026-07-15 15:03:08.953275+07	force-cancelled by user	mrlsibbwhnxihh0n0ho	A06
3917	623e373b	AGV01	go_charge	\N	running	2026-07-15 15:03:42.3381+07	\N	\N	\N	\N	hmi_station_trigger
3921	c290cf20	AGV01	go_to	81	cancelled	2026-07-15 15:15:22.762075+07	2026-07-15 15:15:22.763671+07	2026-07-15 15:21:00.45474+07	force-cancelled by user	mrlt0ie6638st1487md	A06
3919	df20b245	AGV01	go_to	104	cancelled	2026-07-15 15:14:16.714969+07	\N	2026-07-15 15:21:00.45474+07	cancelled by user	mrlt0ie6638st1487md	A06
3922	8e7079f7	AGV01	go_charge	\N	cancelled	2026-07-15 15:17:04.34723+07	\N	2026-07-15 15:21:00.45474+07	cancelled by user	\N	hmi_station_trigger
3920	d1cfc913	AGV01	go_charge	\N	cancelled	2026-07-15 15:14:16.71599+07	\N	2026-07-15 15:21:00.45474+07	cancelled by user	mrlt0ie6638st1487md	A06
3923	4b1c0bd7	AGV01	go_charge	\N	cancelled	2026-07-15 15:19:27.225185+07	\N	2026-07-15 15:21:00.45474+07	cancelled by user	\N	hmi_station_trigger
3924	3483e94b	AGV01	go_charge	\N	cancelled	2026-07-15 15:22:08.563346+07	2026-07-15 15:22:08.563346+07	2026-07-15 15:24:49.133797+07	force-cancelled by user	\N	hmi_station_trigger
3925	10c7189c	AGV01	go_charge	\N	cancelled	2026-07-15 15:25:03.153656+07	2026-07-15 15:25:03.153656+07	2026-07-15 15:29:15.68449+07	force-cancelled by user	mrlteda5j2i244rx7t	Sạc Pin
3928	b6ff7633	AGV01	go_to	82	cancelled	2026-07-15 15:34:45.841906+07	2026-07-15 15:34:45.841906+07	2026-07-15 15:44:43.296102+07	force-cancelled by user	\N	\N
3929	aca3481f	AGV01	go_to	204	cancelled	2026-07-15 15:34:45.840906+07	\N	2026-07-15 15:44:43.297042+07	cancelled by user	\N	\N
3926	ef5018c3	AGV01	go_charge	\N	cancelled	2026-07-15 15:34:45.83991+07	\N	2026-07-15 15:44:43.297042+07	cancelled by user	\N	\N
3930	f73f0ebe	AGV01	go_to	104	cancelled	2026-07-15 15:34:45.840906+07	\N	2026-07-15 15:44:43.297042+07	cancelled by user	\N	\N
3931	335d8936	AGV01	go_to	82	cancelled	2026-07-15 15:34:46.349496+07	\N	2026-07-15 15:44:43.297042+07	cancelled by user	\N	\N
3936	d0f24a30	AGV01	go_to	82	completed	2026-07-15 15:45:02.182515+07	2026-07-15 15:45:02.182515+07	2026-07-15 15:46:13.438702+07	off_route	\N	\N
3939	a3c3ee26	AGV01	go_to	81	failed	2026-07-15 15:47:37.593336+07	2026-07-15 15:47:37.595332+07	2026-07-15 15:47:37.649392+07	auto-dispatch failed	\N	\N
3938	5771c883	AGV01	go_to	81	completed	2026-07-15 15:46:13.437661+07	2026-07-15 15:46:13.43966+07	2026-07-15 15:47:37.594331+07	off_route	\N	\N
3940	c7430977	AGV01	go_charge	\N	completed	2026-07-15 15:53:10.186432+07	2026-07-15 15:53:10.186432+07	2026-07-15 15:53:21.088046+07	off_route	\N	hmi_station_trigger
3935	8a7b1751	AGV01	go_to	104	cancelled	2026-07-15 15:45:02.181521+07	\N	2026-07-15 15:48:13.452147+07	cancelled by user	\N	\N
3937	7dab413e	AGV01	go_to	82	cancelled	2026-07-15 15:45:02.380163+07	\N	2026-07-15 15:48:13.452147+07	cancelled by user	\N	\N
3934	9413f893	AGV01	go_to	204	cancelled	2026-07-15 15:45:02.181521+07	\N	2026-07-15 15:48:13.452147+07	cancelled by user	\N	\N
3933	1c27b012	AGV01	go_to	81	cancelled	2026-07-15 15:45:02.181521+07	\N	2026-07-15 15:48:13.452147+07	cancelled by user	\N	\N
3932	dff98105	AGV01	go_charge	\N	cancelled	2026-07-15 15:45:02.180517+07	\N	2026-07-15 15:48:13.452147+07	cancelled by user	\N	\N
3941	57e48ee6	AGV01	go_charge	\N	cancelled	2026-07-15 15:53:10.212498+07	\N	2026-07-15 15:53:38.552183+07	cancelled by user	\N	hmi_station_trigger
3942	4b2dc5fe	AGV01	go_to	82	failed	2026-07-15 15:53:21.086997+07	2026-07-15 15:53:21.089001+07	2026-07-15 15:53:21.127999+07	auto-dispatch failed	\N	hmi_station_trigger
3947	1cc03764	AGV01	go_to	104	cancelled	2026-07-15 15:54:56.81317+07	\N	2026-07-15 15:55:11.878179+07	cancelled by user	\N	\N
3946	ff9f1d8a	AGV01	go_to	82	failed	2026-07-15 15:54:56.81317+07	2026-07-15 15:54:56.81317+07	2026-07-15 15:54:57.245656+07	auto-dispatch failed	\N	\N
3943	39213356	AGV01	go_to	81	cancelled	2026-07-15 15:54:56.81317+07	\N	2026-07-15 15:55:11.878179+07	cancelled by user	\N	\N
3944	ce9476f7	AGV01	go_to	204	cancelled	2026-07-15 15:54:56.81317+07	\N	2026-07-15 15:55:11.878179+07	cancelled by user	\N	\N
3945	647adb01	AGV01	go_charge	\N	cancelled	2026-07-15 15:54:56.812171+07	\N	2026-07-15 15:55:11.878179+07	cancelled by user	\N	\N
3948	ec3e3eb0	AGV01	go_charge	\N	completed	2026-07-15 15:57:45.73087+07	2026-07-15 15:57:45.73087+07	2026-07-15 15:58:27.839942+07		\N	hmi_station_trigger
3949	f1c13d73	AGV01	go_charge	\N	running	2026-07-15 15:57:45.768872+07	2026-07-15 15:58:27.840976+07	\N		\N	hmi_station_trigger
3980	683b3c22	AGV01	go_charge	\N	cancelled	2026-07-15 16:22:51.210008+07	\N	2026-07-15 16:23:15.311685+07	cancelled by user	\N	hmi_station_trigger
3954	e0ff76a8	AGV01	go_to	82	completed	2026-07-15 16:01:33.117633+07	2026-07-15 16:01:33.117633+07	2026-07-15 16:02:55.472842+07	off_route	\N	\N
3956	787bf306	AGV01	go_to	81	failed	2026-07-15 16:02:55.469844+07	2026-07-15 16:02:55.476854+07	2026-07-15 16:02:55.544375+07	auto-dispatch failed	\N	\N
3955	d6c694e2	AGV01	go_to	82	cancelled	2026-07-15 16:01:33.581923+07	\N	2026-07-15 16:04:40.919228+07	cancelled by user	\N	\N
3953	e082cb67	AGV01	go_to	103	cancelled	2026-07-15 16:01:33.117633+07	\N	2026-07-15 16:04:40.919228+07	cancelled by user	\N	\N
3952	42fcd1e5	AGV01	go_to	203	cancelled	2026-07-15 16:01:33.116625+07	\N	2026-07-15 16:04:40.919228+07	cancelled by user	\N	\N
3951	0a700c73	AGV01	go_to	81	cancelled	2026-07-15 16:01:33.116625+07	\N	2026-07-15 16:04:40.919228+07	cancelled by user	\N	\N
3950	a6c68128	AGV01	go_charge	\N	cancelled	2026-07-15 16:01:33.116625+07	\N	2026-07-15 16:04:40.919228+07	cancelled by user	\N	\N
3957	92c76c57	AGV01	go_charge	\N	cancelled	2026-07-15 16:05:15.469842+07	2026-07-15 16:05:15.469842+07	2026-07-15 16:06:09.075374+07	force-cancelled by user	\N	hmi_station_trigger
3962	c219480a	AGV01	go_to	82	completed	2026-07-15 16:09:48.243442+07	2026-07-15 16:09:48.243442+07	2026-07-15 16:12:25.205689+07	event:continue	\N	\N
3963	5cee998b	AGV01	go_to	82	completed	2026-07-15 16:09:48.830013+07	2026-07-15 16:12:25.207686+07	2026-07-15 16:12:42.535902+07	hook_raised	\N	\N
3960	f485df51	AGV01	go_to	104	cancelled	2026-07-15 16:09:48.242429+07	2026-07-15 16:12:42.53691+07	2026-07-15 16:12:58.342155+07	force-cancelled by user	\N	\N
3961	de5196c8	AGV01	go_to	204	cancelled	2026-07-15 16:09:48.242429+07	\N	2026-07-15 16:12:58.342155+07	cancelled by user	\N	\N
3959	7586ab2c	AGV01	go_to	81	cancelled	2026-07-15 16:09:48.242429+07	\N	2026-07-15 16:12:58.342155+07	cancelled by user	\N	\N
3958	654aa3e9	AGV01	go_charge	\N	cancelled	2026-07-15 16:09:48.241431+07	\N	2026-07-15 16:12:58.342155+07	cancelled by user	\N	\N
3964	99918722	AGV01	go_charge	\N	completed	2026-07-15 16:18:19.085878+07	2026-07-15 16:18:19.085878+07	2026-07-15 16:18:28.198297+07		\N	hmi_station_trigger
3965	1b6e68f8	AGV01	go_charge	\N	completed	2026-07-15 16:18:19.237429+07	2026-07-15 16:18:28.198297+07	2026-07-15 16:18:29.948299+07	charge_arrived	\N	hmi_station_trigger
3966	2ce2cd31	AGV01	go_charge	\N	cancelled	2026-07-15 16:19:06.487338+07	2026-07-15 16:19:06.487338+07	2026-07-15 16:21:08.387132+07	force-cancelled by user	\N	hmi_station_trigger
3967	941108eb	AGV01	go_charge	\N	cancelled	2026-07-15 16:20:50.912241+07	\N	2026-07-15 16:21:08.387132+07	cancelled by user	\N	hmi_station_trigger
3968	4d7de3c1	AGV01	go_charge	\N	cancelled	2026-07-15 16:20:56.509598+07	\N	2026-07-15 16:21:08.387132+07	cancelled by user	\N	hmi_station_trigger
3969	87fae181	AGV01	go_charge	\N	cancelled	2026-07-15 16:20:56.649804+07	\N	2026-07-15 16:21:08.387132+07	cancelled by user	\N	hmi_station_trigger
3970	443984c9	AGV01	go_charge	\N	completed	2026-07-15 16:21:31.288572+07	2026-07-15 16:21:31.288572+07	2026-07-15 16:21:34.311447+07	charge_arrived	\N	hmi_station_trigger
3974	880aac91	AGV01	go_to	104	cancelled	2026-07-15 16:21:44.879048+07	\N	2026-07-15 16:23:15.311685+07	cancelled by user	\N	\N
3971	fb5a5f9f	AGV01	go_charge	\N	cancelled	2026-07-15 16:21:44.878082+07	\N	2026-07-15 16:23:15.311685+07	cancelled by user	\N	\N
3973	4dc8abb6	AGV01	go_to	204	cancelled	2026-07-15 16:21:44.879048+07	\N	2026-07-15 16:23:15.311685+07	cancelled by user	\N	\N
3972	a8709510	AGV01	go_to	81	cancelled	2026-07-15 16:21:44.879048+07	\N	2026-07-15 16:23:15.311685+07	cancelled by user	\N	\N
3977	088e3bb1	AGV01	go_charge	\N	cancelled	2026-07-15 16:22:20.678336+07	\N	2026-07-15 16:23:15.311685+07	cancelled by user	\N	hmi_station_trigger
3975	1cdfdadd	AGV01	go_to	82	cancelled	2026-07-15 16:21:44.880049+07	2026-07-15 16:21:44.880049+07	2026-07-15 16:23:15.310684+07	force-cancelled by user	\N	\N
3976	03a9b945	AGV01	go_to	82	cancelled	2026-07-15 16:21:45.23819+07	\N	2026-07-15 16:23:15.311685+07	cancelled by user	\N	\N
3978	4180c1bf	AGV01	go_charge	\N	cancelled	2026-07-15 16:22:50.308528+07	\N	2026-07-15 16:23:15.311685+07	cancelled by user	\N	hmi_station_trigger
3979	827411ee	AGV01	go_charge	\N	cancelled	2026-07-15 16:22:50.612278+07	\N	2026-07-15 16:23:15.311685+07	cancelled by user	\N	hmi_station_trigger
3983	0fa8d383	AGV01	go_to	204	cancelled	2026-07-15 16:23:33.74434+07	\N	2026-07-15 16:26:45.743518+07	cancelled by user	\N	\N
3984	b9239249	AGV01	go_to	82	cancelled	2026-07-15 16:23:33.74434+07	2026-07-15 16:23:33.74434+07	2026-07-15 16:26:45.742518+07	force-cancelled by user	\N	\N
3986	38046ff4	AGV01	go_to	82	cancelled	2026-07-15 16:23:34.353708+07	\N	2026-07-15 16:26:45.743518+07	cancelled by user	\N	\N
3985	9d4b7697	AGV01	go_to	104	cancelled	2026-07-15 16:23:33.74434+07	\N	2026-07-15 16:26:45.743518+07	cancelled by user	\N	\N
3982	bd3909d6	AGV01	go_to	81	cancelled	2026-07-15 16:23:33.74434+07	\N	2026-07-15 16:26:45.743518+07	cancelled by user	\N	\N
3981	46fe70a7	AGV01	go_charge	\N	cancelled	2026-07-15 16:23:33.743334+07	\N	2026-07-15 16:26:45.743518+07	cancelled by user	\N	\N
4001	f91ca5a9	AGV01	go_charge	\N	completed	2026-07-15 16:41:12.474616+07	2026-07-15 16:41:12.474616+07	2026-07-15 16:41:15.477276+07	charge_arrived	\N	hmi_station_trigger
3991	77ff571a	AGV01	go_to	82	completed	2026-07-15 16:26:51.453089+07	2026-07-15 16:26:51.453089+07	2026-07-15 16:29:16.76546+07	event:continue	\N	\N
3992	65737c7f	AGV01	go_to	82	completed	2026-07-15 16:26:51.504067+07	2026-07-15 16:29:16.766425+07	2026-07-15 16:29:39.500784+07	hook_raised	\N	\N
3988	2382d88e	AGV01	go_charge	\N	cancelled	2026-07-15 16:26:51.450162+07	2026-07-15 16:35:31.128275+07	2026-07-15 16:37:20.8538+07	force-cancelled by user	\N	\N
3990	85c444ac	AGV01	go_to	104	completed	2026-07-15 16:26:51.452096+07	2026-07-15 16:29:39.500784+07	2026-07-15 16:29:41.187712+07	hook_already_raised	\N	\N
3989	8a27f450	AGV01	go_to	204	completed	2026-07-15 16:26:51.452096+07	2026-07-15 16:29:41.187712+07	2026-07-15 16:31:53.377654+07	off_route	\N	\N
3993	3dbcefc5	AGV01	go_to	204	completed	2026-07-15 16:31:53.376649+07	2026-07-15 16:31:53.377654+07	2026-07-15 16:33:40.066095+07	lifecycle:picking:confirmed	\N	\N
3987	b4b397a9	AGV01	go_to	81	completed	2026-07-15 16:26:51.451098+07	2026-07-15 16:33:40.066095+07	2026-07-15 16:35:29.437161+07	hook_raised	\N	\N
3994	1414c0bd	AGV01	go_to	81	completed	2026-07-15 16:33:40.11075+07	2026-07-15 16:35:29.43816+07	2026-07-15 16:35:31.127266+07	hook_already_raised	\N	\N
3996	1e278ccf	AGV01	go_to	81	cancelled	2026-07-15 16:39:44.0283+07	\N	2026-07-15 16:40:13.765476+07	cancelled by user	\N	\N
3999	2b90fdb7	AGV01	go_to	104	cancelled	2026-07-15 16:39:44.0283+07	\N	2026-07-15 16:40:13.765476+07	cancelled by user	\N	\N
3998	e04c0183	AGV01	go_to	82	cancelled	2026-07-15 16:39:44.0283+07	2026-07-15 16:39:44.029732+07	2026-07-15 16:40:13.764423+07	force-cancelled by user	\N	\N
3997	9b538198	AGV01	go_to	204	cancelled	2026-07-15 16:39:44.0283+07	\N	2026-07-15 16:40:13.765476+07	cancelled by user	\N	\N
3995	44c55f07	AGV01	go_charge	\N	cancelled	2026-07-15 16:39:44.027318+07	\N	2026-07-15 16:40:13.765476+07	cancelled by user	\N	\N
4000	2237a235	AGV01	go_charge	\N	completed	2026-07-15 16:41:06.60919+07	2026-07-15 16:41:06.60919+07	2026-07-15 16:41:10.329118+07	charge_arrived	\N	hmi_station_trigger
4002	da93498c	AGV01	go_charge	\N	completed	2026-07-15 16:41:17.960653+07	2026-07-15 16:41:17.960653+07	2026-07-15 16:41:20.835665+07	charge_arrived	\N	hmi_station_trigger
4003	f6b9b39b	AGV01	go_charge	\N	completed	2026-07-15 16:41:34.413215+07	2026-07-15 16:41:34.413215+07	2026-07-15 16:41:37.37026+07	charge_arrived	\N	hmi_station_trigger
4004	514d318c	AGV01	go_charge	\N	completed	2026-07-15 16:41:51.495942+07	2026-07-15 16:41:51.495942+07	2026-07-15 16:41:54.562566+07	charge_arrived	\N	hmi_station_trigger
4005	37982016	AGV01	go_charge	\N	cancelled	2026-07-15 16:41:54.929444+07	2026-07-15 16:41:54.929444+07	2026-07-15 16:42:30.05418+07	force-cancelled by user	\N	hmi_station_trigger
4006	f6967324	AGV01	go_charge	\N	cancelled	2026-07-15 16:42:42.469334+07	2026-07-15 16:42:42.469334+07	2026-07-15 16:43:05.260236+07	force-cancelled by user	mrlw68eikpsedd6qy1g	Sạc Pin
4007	df03e238	AGV01	go_charge	\N	cancelled	2026-07-15 16:42:55.500724+07	\N	2026-07-15 16:43:05.260236+07	cancelled by user	\N	hmi_station_trigger
4008	0fc907cb	AGV01	go_charge	\N	cancelled	2026-07-15 16:43:47.91661+07	2026-07-15 16:43:47.91661+07	2026-07-15 16:44:48.708956+07	force-cancelled by user	mrlw7mxf8s5ux15x4l	Sạc Pin
4009	2d2503fa	AGV01	go_charge	\N	completed	2026-07-15 16:56:42.282097+07	2026-07-15 16:56:42.282097+07	2026-07-15 16:56:45.454701+07	charge_arrived	\N	hmi_station_trigger
4010	a8c3d0e1	AGV01	go_charge	\N	completed	2026-07-15 16:57:11.356486+07	2026-07-15 16:57:11.356486+07	2026-07-15 16:57:14.471602+07	charge_arrived	\N	hmi_station_trigger
4011	10ac5ca0	AGV01	go_charge	\N	completed	2026-07-15 16:57:41.061604+07	2026-07-15 16:57:41.061604+07	2026-07-15 16:58:25.104934+07	charge_arrived	\N	hmi_station_trigger
4013	f02690eb	AGV01	go_to	81	completed	2026-07-15 16:58:40.445002+07	2026-07-15 17:03:18.913986+07	2026-07-15 17:05:20.856075+07	hook_raised	\N	\N
4015	57504535	AGV01	go_to	82	completed	2026-07-15 16:58:40.445002+07	2026-07-15 16:58:40.445962+07	2026-07-15 17:00:09.53163+07	event:continue	\N	\N
4043	7e2ca4ca	AGV01	go_to	111	completed	2026-07-16 10:14:34.614578+07	2026-07-16 10:16:04.442776+07	2026-07-16 10:18:42.630494+07	hook_raised	\N	\N
4016	ccfcaed6	AGV01	go_to	104	completed	2026-07-15 16:58:40.445002+07	2026-07-15 17:00:09.532649+07	2026-07-15 17:02:23.408478+07	hook_raised	\N	\N
4063	88bed3b5	AGV01	go_to	103	completed	2026-07-16 11:38:15.012114+07	2026-07-16 11:41:48.968188+07	2026-07-16 11:44:25.270693+07	hook_raised	\N	\N
4014	1667d6ec	AGV01	go_to	204	completed	2026-07-15 16:58:40.445002+07	2026-07-15 17:02:23.409651+07	2026-07-15 17:03:18.913986+07	event:continue	\N	\N
4042	156ef8b8	AGV01	go_to	211	completed	2026-07-16 10:14:34.614578+07	2026-07-16 10:18:42.631483+07	2026-07-16 10:22:48.660534+07	event:continue	\N	\N
4012	19e9e1b1	AGV01	go_charge	\N	completed	2026-07-15 16:58:40.445002+07	2026-07-15 17:05:20.856075+07	2026-07-15 17:05:22.655385+07	hook_already_raised	\N	\N
4020	31d8b3b7	AGV01	go_to	211	cancelled	2026-07-16 09:10:21.182012+07	\N	2026-07-16 09:10:39.564843+07	cancelled by user	\N	\N
4021	4e7dd874	AGV01	go_to	82	cancelled	2026-07-16 09:10:21.183021+07	2026-07-16 09:10:21.183021+07	2026-07-16 09:10:39.564843+07	force-cancelled by user	\N	\N
4019	80bdbfb2	AGV01	go_to	111	cancelled	2026-07-16 09:10:21.182012+07	\N	2026-07-16 09:10:39.564843+07	cancelled by user	\N	\N
4017	e6291477	AGV01	go_charge	\N	cancelled	2026-07-16 09:10:21.181011+07	\N	2026-07-16 09:10:39.564843+07	cancelled by user	\N	\N
4018	bc9e6904	AGV01	go_to	81	cancelled	2026-07-16 09:10:21.182012+07	\N	2026-07-16 09:10:39.564843+07	cancelled by user	\N	\N
4022	c8ccf0b2	AGV01	go_charge	\N	completed	2026-07-16 09:12:08.303472+07	2026-07-16 09:12:08.303472+07	2026-07-16 09:12:54.463783+07	charge_arrived	mrmvineha8kw0ilzpzh	Sạc Pin
4062	1aacf264	AGV01	go_to	203	completed	2026-07-16 11:38:15.012114+07	2026-07-16 11:44:25.270693+07	2026-07-16 11:45:20.981694+07	event:continue	\N	\N
4040	16612c7f	AGV01	go_to	81	completed	2026-07-16 10:14:34.614578+07	2026-07-16 10:22:48.662424+07	2026-07-16 10:25:51.337959+07	hook_already_raised	\N	\N
4027	e70695a6	AGV01	go_to	82	completed	2026-07-16 09:18:27.170399+07	2026-07-16 09:18:27.175387+07	2026-07-16 09:20:25.170247+07	event:continue	\N	\N
4026	364191c3	AGV01	go_to	111	completed	2026-07-16 09:18:27.167392+07	2026-07-16 09:20:25.172246+07	2026-07-16 09:23:20.762293+07	hook_raised	\N	\N
4039	64b7486b	AGV01	go_charge	\N	completed	2026-07-16 10:14:34.614578+07	2026-07-16 10:25:51.338968+07	2026-07-16 10:25:52.991417+07	hook_already_raised	\N	\N
4025	a5f7a850	AGV01	go_to	211	completed	2026-07-16 09:18:27.165398+07	2026-07-16 09:23:20.763257+07	2026-07-16 09:24:35.648732+07	event:continue	\N	\N
4024	96353a41	AGV01	go_to	81	completed	2026-07-16 09:18:27.163407+07	2026-07-16 09:24:35.649777+07	2026-07-16 09:27:45.404256+07	hook_raised	\N	\N
4023	339ed837	AGV01	go_charge	\N	completed	2026-07-16 09:18:27.162399+07	2026-07-16 09:27:45.405243+07	2026-07-16 09:27:47.15921+07	hook_already_raised	\N	\N
4028	735b2b0a	AGV01	go_charge	\N	queued	2026-07-16 09:48:10.04403+07	\N	\N	\N	\N	\N
4029	a2da91fe	AGV01	go_to	81	queued	2026-07-16 09:48:10.046023+07	\N	\N	\N	\N	\N
4032	1950398d	AGV01	go_to	82	completed	2026-07-16 09:48:10.046023+07	2026-07-16 09:48:10.04702+07	2026-07-16 09:49:09.460489+07	hook_already_raised	\N	\N
4030	01b45a9f	AGV01	go_to	211	running	2026-07-16 09:48:10.046023+07	2026-07-16 09:49:11.17849+07	\N		\N	\N
4031	be14aa1a	AGV01	go_to	111	completed	2026-07-16 09:48:10.046023+07	2026-07-16 09:49:09.46249+07	2026-07-16 09:49:11.17849+07	hook_already_raised	\N	\N
4033	a8746a91	AGV01	go_charge	\N	completed	2026-07-16 09:57:38.782007+07	2026-07-16 09:57:38.782007+07	2026-07-16 09:58:25.987213+07	charge_arrived	mrmx568lwwyczsapa8	Sạc Pin
4059	6a8d2925	AGV01	go_to	82	completed	2026-07-16 11:26:45.200283+07	2026-07-16 11:26:45.200283+07	2026-07-16 11:28:17.576156+07	event:continue	\N	\N
4038	19cd93c8	AGV01	go_to	82	completed	2026-07-16 09:59:48.070174+07	2026-07-16 09:59:48.070174+07	2026-07-16 10:01:23.43736+07	event:continue	\N	\N
4067	42183032	AGV01	go_charge	\N	cancelled	2026-07-16 13:36:29.716674+07	\N	2026-07-16 13:38:43.450526+07	cancelled by user	\N	\N
4037	f160a2de	AGV01	go_to	110	completed	2026-07-16 09:59:48.070174+07	2026-07-16 10:01:23.438266+07	2026-07-16 10:04:23.197203+07	hook_raised	\N	\N
4048	e7ed259b	AGV01	go_to	82	completed	2026-07-16 10:56:37.087571+07	2026-07-16 10:56:37.088509+07	2026-07-16 10:57:53.796344+07	event:continue	\N	\N
4036	bcf6cafe	AGV01	go_to	210	completed	2026-07-16 09:59:48.070174+07	2026-07-16 10:04:23.198324+07	2026-07-16 10:05:53.46153+07	event:continue	\N	\N
4058	258492e3	AGV01	go_to	110	completed	2026-07-16 11:26:45.200283+07	2026-07-16 11:28:17.577409+07	2026-07-16 11:30:54.442057+07	hook_raised	\N	\N
4034	b3bacd9c	AGV01	go_to	81	completed	2026-07-16 09:59:48.069182+07	2026-07-16 10:05:53.462584+07	2026-07-16 10:08:37.850479+07	hook_raised	\N	\N
4035	dba728ef	AGV01	go_charge	\N	completed	2026-07-16 09:59:48.069182+07	2026-07-16 10:08:37.851595+07	2026-07-16 10:08:39.536029+07	hook_already_raised	\N	\N
4041	ca473ef5	AGV01	go_to	82	completed	2026-07-16 10:14:34.614578+07	2026-07-16 10:14:34.615624+07	2026-07-16 10:16:04.441814+07	event:continue	\N	\N
4061	4e6a3058	AGV01	go_to	81	completed	2026-07-16 11:38:15.011111+07	2026-07-16 11:45:20.982695+07	2026-07-16 11:47:17.20523+07	hook_raised	\N	\N
4057	0f72f97b	AGV01	go_to	210	completed	2026-07-16 11:26:45.200283+07	2026-07-16 11:30:54.442969+07	2026-07-16 11:32:02.577447+07	event:continue	\N	\N
4047	37ff7a2d	AGV01	go_to	111	completed	2026-07-16 10:56:37.086507+07	2026-07-16 10:57:53.797355+07	2026-07-16 11:00:44.477123+07	hook_raised	\N	\N
4069	b5d222b0	AGV01	go_to	110	cancelled	2026-07-16 13:36:29.719671+07	\N	2026-07-16 13:38:43.450526+07	cancelled by user	\N	\N
4046	92bc2f23	AGV01	go_to	211	completed	2026-07-16 10:56:37.086507+07	2026-07-16 11:00:44.478137+07	2026-07-16 11:01:50.68164+07	event:continue	\N	\N
4055	5149d998	AGV01	go_to	81	completed	2026-07-16 11:26:45.199296+07	2026-07-16 11:32:02.578443+07	2026-07-16 11:36:23.801246+07	hook_raised	\N	\N
4045	566713b5	AGV01	go_to	81	completed	2026-07-16 10:56:37.085511+07	2026-07-16 11:01:50.68263+07	2026-07-16 11:04:45.592687+07	hook_raised	\N	\N
4044	18e85c53	AGV01	go_charge	\N	completed	2026-07-16 10:56:37.085511+07	2026-07-16 11:04:45.593685+07	2026-07-16 11:04:47.298135+07	hook_already_raised	\N	\N
4053	23802060	AGV01	go_to	82	cancelled	2026-07-16 11:11:54.139724+07	2026-07-16 11:11:54.139724+07	2026-07-16 11:20:49.735171+07	force-cancelled by user	\N	\N
4051	38a87f1b	AGV01	go_to	111	cancelled	2026-07-16 11:11:54.139724+07	\N	2026-07-16 11:20:49.736182+07	cancelled by user	\N	\N
4052	6ba4f7db	AGV01	go_to	211	cancelled	2026-07-16 11:11:54.13872+07	\N	2026-07-16 11:20:49.736182+07	cancelled by user	\N	\N
4050	c67319ea	AGV01	go_to	81	cancelled	2026-07-16 11:11:54.13872+07	\N	2026-07-16 11:20:49.736182+07	cancelled by user	\N	\N
4049	d780ffb2	AGV01	go_charge	\N	cancelled	2026-07-16 11:11:54.13872+07	\N	2026-07-16 11:20:49.736182+07	cancelled by user	\N	\N
4054	11020aef	AGV01	go_charge	\N	completed	2026-07-16 11:25:31.633082+07	2026-07-16 11:25:31.633082+07	2026-07-16 11:26:11.762347+07	charge_arrived	mrn0a6slavudymg8qv	Sạc Pin
4056	9ea84c3c	AGV01	go_charge	\N	completed	2026-07-16 11:26:45.199296+07	2026-07-16 11:36:23.802344+07	2026-07-16 11:36:25.486642+07	hook_already_raised	\N	\N
4064	65be721c	AGV01	go_to	82	completed	2026-07-16 11:38:15.012114+07	2026-07-16 11:38:15.013147+07	2026-07-16 11:41:48.967096+07	event:continue	\N	\N
4066	f961050b	AGV01	go_to	81	cancelled	2026-07-16 13:36:29.718676+07	\N	2026-07-16 13:38:43.450526+07	cancelled by user	\N	\N
4070	f155f548	AGV01	go_to	82	cancelled	2026-07-16 13:36:29.719671+07	2026-07-16 13:36:29.719671+07	2026-07-16 13:38:43.44952+07	force-cancelled by user	\N	\N
4060	59f378ef	AGV01	go_charge	\N	completed	2026-07-16 11:38:15.011111+07	2026-07-16 11:47:17.207228+07	2026-07-16 11:47:18.901968+07	hook_already_raised	\N	\N
4065	dba54f42	AGV01	go_charge	\N	completed	2026-07-16 13:32:56.981933+07	2026-07-16 13:32:56.981933+07	2026-07-16 13:33:32.916499+07	charge_arrived	mrn4u208f1zdagjtwu6	Sạc Pin
4068	acd2e8ed	AGV01	go_to	210	cancelled	2026-07-16 13:36:29.718676+07	\N	2026-07-16 13:38:43.450526+07	cancelled by user	\N	\N
4071	ce1dc0f2	AGV01	go_charge	\N	completed	2026-07-16 13:39:10.426733+07	2026-07-16 13:39:10.426733+07	2026-07-16 13:39:57.678911+07	charge_arrived	mrn5225yxvzdsu440be	Sạc Pin
4074	1301e302	AGV01	go_to	110	cancelled	2026-07-16 13:40:31.561125+07	\N	2026-07-16 13:46:37.125268+07	cancelled by user	\N	\N
4076	68bfca73	AGV01	go_to	82	cancelled	2026-07-16 13:40:31.561125+07	2026-07-16 13:40:31.561125+07	2026-07-16 13:46:37.125268+07	force-cancelled by user	\N	\N
4073	2de38c96	AGV01	go_to	210	cancelled	2026-07-16 13:40:31.561125+07	\N	2026-07-16 13:46:37.125268+07	cancelled by user	\N	\N
4075	51c38ee0	AGV01	go_to	81	cancelled	2026-07-16 13:40:31.561125+07	\N	2026-07-16 13:46:37.125268+07	cancelled by user	\N	\N
4072	fd85299f	AGV01	go_charge	\N	cancelled	2026-07-16 13:40:31.561125+07	\N	2026-07-16 13:46:37.125268+07	cancelled by user	\N	\N
4077	038bdd76	AGV01	go_charge	\N	completed	2026-07-16 13:52:15.532158+07	2026-07-16 13:52:15.532158+07	2026-07-16 13:52:50.940751+07	charge_arrived	\N	hmi_station_trigger
4078	8f43744e	AGV01	go_to	111	cancelled	2026-07-16 13:53:19.090962+07	2026-07-16 13:53:19.090962+07	2026-07-16 13:55:06.890577+07	force-cancelled by user	uamabetqionv	Mobile → Tổ 19 — 111, Tổ 19 — 111
4079	859d8586	AGV01	go_to	111	cancelled	2026-07-16 13:53:19.1592+07	\N	2026-07-16 13:55:06.892609+07	cancelled by user	uamabetqionv	Mobile → Tổ 19 — 111, Tổ 19 — 111
4080	abe05811	AGV01	go_charge	\N	cancelled	2026-07-16 13:53:19.16223+07	\N	2026-07-16 13:55:06.892609+07	cancelled by user	uamabetqionv	Mobile → Tổ 19 — 111, Tổ 19 — 111
4081	2a65c001	AGV01	go_charge	\N	completed	2026-07-16 13:56:25.40622+07	2026-07-16 13:56:25.40622+07	2026-07-16 13:56:29.802899+07	charge_arrived	\N	hmi_station_trigger
4082	0e782ba8	AGV01	go_charge	\N	completed	2026-07-16 13:56:49.257755+07	2026-07-16 13:56:49.257755+07	2026-07-16 13:57:53.702256+07	charge_arrived	mrn5or4wmti4dnhhufr	Sạc Pin
4083	e3530622	AGV01	go_to	110	completed	2026-07-16 13:58:11.70814+07	2026-07-16 13:58:11.70814+07	2026-07-16 14:01:51.226164+07	hook_already_raised	fs6y5vlcxhbg	Mobile → Tổ 31 — 110, Tổ 31 — 110
4102	896b0c7d	AGV01	go_to	108	cancelled	2026-07-16 14:22:51.739233+07	\N	2026-07-16 14:23:49.593232+07	cancelled by user	l1dw8qu5tba7	Mobile → Tổ 20 — 108, Tổ 20 — 108
4101	6445b8cb	AGV01	go_to	108	cancelled	2026-07-16 14:22:51.700157+07	2026-07-16 14:22:51.700157+07	2026-07-16 14:23:49.593232+07	force-cancelled by user	l1dw8qu5tba7	Mobile → Tổ 20 — 108, Tổ 20 — 108
4085	0efa0225	AGV01	go_to	110	completed	2026-07-16 13:58:11.766149+07	2026-07-16 14:01:51.227166+07	2026-07-16 14:01:51.230169+07	already_at_dest	fs6y5vlcxhbg	Mobile → Tổ 31 — 110, Tổ 31 — 110
4084	2afb00a0	AGV01	go_charge	\N	completed	2026-07-16 13:58:11.769149+07	2026-07-16 14:01:51.233291+07	2026-07-16 14:07:03.96579+07	lifecycle:picking:confirmed	fs6y5vlcxhbg	Mobile → Tổ 31 — 110, Tổ 31 — 110
4103	5e361947	AGV01	go_charge	\N	cancelled	2026-07-16 14:22:51.740226+07	\N	2026-07-16 14:23:49.593232+07	cancelled by user	l1dw8qu5tba7	Mobile → Tổ 20 — 108, Tổ 20 — 108
4089	bf2e04f7	AGV01	go_charge	\N	cancelled	2026-07-16 14:07:04.450304+07	\N	2026-07-16 14:07:28.37202+07	cancelled by user	\N	hmi_station_trigger
4087	f221bc99	AGV01	go_charge	\N	cancelled	2026-07-16 14:04:47.961158+07	\N	2026-07-16 14:07:28.37202+07	cancelled by user	\N	hmi_station_trigger
4086	ebe572f9	AGV01	go_charge	\N	cancelled	2026-07-16 14:04:46.930641+07	2026-07-16 14:07:03.96579+07	2026-07-16 14:07:28.37102+07	force-cancelled by user	\N	hmi_station_trigger
4088	c4524021	AGV01	go_charge	\N	cancelled	2026-07-16 14:04:48.880884+07	\N	2026-07-16 14:07:28.37202+07	cancelled by user	\N	hmi_station_trigger
4090	b636bf3e	AGV01	go_charge	\N	cancelled	2026-07-16 14:07:38.573762+07	2026-07-16 14:07:38.573762+07	2026-07-16 14:15:32.41107+07	force-cancelled by user	mrn62o5es38eff3zkf	Sạc Pin
4091	d7079027	AGV01	go_charge	\N	cancelled	2026-07-16 14:14:59.887927+07	\N	2026-07-16 14:15:32.412073+07	cancelled by user	\N	hmi_station_trigger
4092	175d99c1	AGV01	go_charge	\N	completed	2026-07-16 14:15:39.616472+07	2026-07-16 14:15:39.616472+07	2026-07-16 14:16:19.397997+07	charge_arrived	\N	hmi_station_trigger
4093	83b29b6f	AGV01	go_to	111	cancelled	2026-07-16 14:16:39.455174+07	2026-07-16 14:16:39.455174+07	2026-07-16 14:17:55.653617+07	force-cancelled by user	pvyit3rgjoiz	Mobile → Tổ 19 — 111, Tổ 19 — 111
4095	fbdf2a60	AGV01	go_charge	\N	cancelled	2026-07-16 14:16:39.581261+07	\N	2026-07-16 14:17:55.653617+07	cancelled by user	pvyit3rgjoiz	Mobile → Tổ 19 — 111, Tổ 19 — 111
4094	1e0d3700	AGV01	go_to	111	cancelled	2026-07-16 14:16:39.560266+07	\N	2026-07-16 14:17:55.653617+07	cancelled by user	pvyit3rgjoiz	Mobile → Tổ 19 — 111, Tổ 19 — 111
4096	76137c84	AGV01	go_charge	\N	completed	2026-07-16 14:18:01.529837+07	2026-07-16 14:18:01.529837+07	2026-07-16 14:18:46.201676+07	charge_arrived	\N	hmi_station_trigger
4097	b6b4be18	AGV01	go_to	81	completed	2026-07-16 14:19:03.553263+07	2026-07-16 14:19:03.553263+07	2026-07-16 14:20:30.288136+07	lifecycle:picking:confirmed	bbthovvuez6o	Mobile → Node 81
4099	86cd970b	AGV01	go_charge	\N	cancelled	2026-07-16 14:20:30.348341+07	\N	2026-07-16 14:20:34.522524+07	cancelled by user	bbthovvuez6o	Mobile → Node 81
4098	0dca2908	AGV01	go_charge	\N	cancelled	2026-07-16 14:19:03.613703+07	2026-07-16 14:20:30.288136+07	2026-07-16 14:20:34.521524+07	force-cancelled by user	bbthovvuez6o	Mobile → Node 81
4104	eed94eaa	AGV01	go_charge	\N	completed	2026-07-16 14:24:16.258486+07	2026-07-16 14:24:16.258486+07	2026-07-16 14:25:03.162513+07	charge_arrived	\N	hmi_station_trigger
4100	0d2148f4	AGV01	go_charge	\N	completed	2026-07-16 14:20:44.90741+07	2026-07-16 14:21:25.989569+07	2026-07-16 14:21:27.721468+07	charge_arrived	\N	\N
4105	837eb352	AGV01	go_to	108	cancelled	2026-07-16 14:25:39.568866+07	2026-07-16 14:25:39.568866+07	2026-07-16 14:26:49.215416+07	force-cancelled by user	j6nre2k69ryj	Mobile → Tổ 20 — 108, Tổ 20 — 108
4106	3254ec36	AGV01	go_to	108	cancelled	2026-07-16 14:25:39.590663+07	\N	2026-07-16 14:26:49.215416+07	cancelled by user	j6nre2k69ryj	Mobile → Tổ 20 — 108, Tổ 20 — 108
4107	6da71414	AGV01	go_charge	\N	cancelled	2026-07-16 14:25:39.590663+07	\N	2026-07-16 14:26:49.215416+07	cancelled by user	j6nre2k69ryj	Mobile → Tổ 20 — 108, Tổ 20 — 108
4108	7e37e1b0	AGV01	go_charge	\N	completed	2026-07-16 14:27:04.773883+07	2026-07-16 14:27:04.773883+07	2026-07-16 14:27:34.989538+07	charge_arrived	\N	hmi_station_trigger
4109	97962255	AGV01	go_to	101	cancelled	2026-07-16 14:27:45.459138+07	2026-07-16 14:27:45.459138+07	2026-07-16 14:28:48.015328+07	force-cancelled by user	jfkdzj0v4hga	Mobile → Tổ 22 — 101, Tổ 22 — 101
4110	9c13a338	AGV01	go_to	101	cancelled	2026-07-16 14:27:45.474028+07	\N	2026-07-16 14:28:48.015328+07	cancelled by user	jfkdzj0v4hga	Mobile → Tổ 22 — 101, Tổ 22 — 101
4111	25ce6932	AGV01	go_charge	\N	cancelled	2026-07-16 14:27:45.474028+07	\N	2026-07-16 14:28:48.015328+07	cancelled by user	jfkdzj0v4hga	Mobile → Tổ 22 — 101, Tổ 22 — 101
4112	5df0b867	AGV01	go_charge	\N	completed	2026-07-16 14:29:00.390206+07	2026-07-16 14:29:00.390206+07	2026-07-16 14:29:44.361365+07	charge_arrived	\N	hmi_station_trigger
4115	780c18d3	AGV01	go_to	111	cancelled	2026-07-16 14:38:39.057532+07	\N	2026-07-16 14:39:27.093201+07	cancelled by user	upb7l6yq4i6d	Mobile → Tổ 19 — 111, Tổ 19 — 111
4113	cafb3b20	AGV01	go_to	82	cancelled	2026-07-16 14:38:38.878205+07	2026-07-16 14:38:38.878205+07	2026-07-16 14:39:27.093201+07	force-cancelled by user	upb7l6yq4i6d	Mobile → Tổ 19 — 111, Tổ 19 — 111
4114	396cf5a4	AGV01	go_to	111	cancelled	2026-07-16 14:38:39.057532+07	\N	2026-07-16 14:39:27.093201+07	cancelled by user	upb7l6yq4i6d	Mobile → Tổ 19 — 111, Tổ 19 — 111
4116	1b6ee031	AGV01	go_charge	\N	cancelled	2026-07-16 14:38:39.058534+07	\N	2026-07-16 14:39:27.093201+07	cancelled by user	upb7l6yq4i6d	Mobile → Tổ 19 — 111, Tổ 19 — 111
4117	2a2ace3c	AGV01	go_to	82	cancelled	2026-07-16 14:39:36.394043+07	2026-07-16 14:39:36.394043+07	2026-07-16 14:39:40.604126+07	force-cancelled by user	oolynizeqns0	Mobile → Tổ 20 — 108, Tổ 20 — 108
4118	0b1ce95f	AGV01	go_to	108	cancelled	2026-07-16 14:39:36.433048+07	\N	2026-07-16 14:39:40.604126+07	cancelled by user	oolynizeqns0	Mobile → Tổ 20 — 108, Tổ 20 — 108
4119	e1501366	AGV01	go_to	108	cancelled	2026-07-16 14:39:36.434043+07	\N	2026-07-16 14:39:40.604126+07	cancelled by user	oolynizeqns0	Mobile → Tổ 20 — 108, Tổ 20 — 108
4120	cf09b1ab	AGV01	go_charge	\N	cancelled	2026-07-16 14:39:36.43805+07	\N	2026-07-16 14:39:40.604126+07	cancelled by user	oolynizeqns0	Mobile → Tổ 20 — 108, Tổ 20 — 108
4121	c7ce9853	AGV01	go_charge	\N	completed	2026-07-16 14:40:41.207496+07	2026-07-16 14:40:41.207496+07	2026-07-16 14:41:25.88785+07	charge_arrived	\N	hmi_station_trigger
4123	07276734	AGV01	go_to	111	cancelled	2026-07-16 14:41:41.279271+07	\N	2026-07-16 14:42:44.735674+07	cancelled by user	qrsevee7f8qg	Mobile → Tổ 19 — 111, Tổ 19 — 111
4122	99d8fc5b	AGV01	go_to	82	cancelled	2026-07-16 14:41:41.240319+07	2026-07-16 14:41:41.240319+07	2026-07-16 14:42:44.735674+07	force-cancelled by user	qrsevee7f8qg	Mobile → Tổ 19 — 111, Tổ 19 — 111
4131	2149e362	AGV01	go_to	108	cancelled	2026-07-16 14:44:33.996162+07	\N	2026-07-16 14:44:46.381459+07	cancelled by user	c4git4yvrxo3	Mobile → Tổ 20 — 108, Tổ 20 — 108
4125	b133f4d0	AGV01	go_charge	\N	cancelled	2026-07-16 14:41:41.281272+07	\N	2026-07-16 14:42:44.735674+07	cancelled by user	qrsevee7f8qg	Mobile → Tổ 19 — 111, Tổ 19 — 111
4127	09478ad1	AGV01	go_charge	\N	cancelled	2026-07-16 14:43:38.714483+07	2026-07-16 14:43:38.714483+07	2026-07-16 14:43:45.805089+07	force-cancelled by user	\N	hmi_station_trigger
4130	7266c360	AGV01	go_to	108	cancelled	2026-07-16 14:44:33.995164+07	\N	2026-07-16 14:44:46.381459+07	cancelled by user	c4git4yvrxo3	Mobile → Tổ 20 — 108, Tổ 20 — 108
4132	9cc71a04	AGV01	go_charge	\N	cancelled	2026-07-16 14:44:33.999158+07	\N	2026-07-16 14:44:46.381459+07	cancelled by user	c4git4yvrxo3	Mobile → Tổ 20 — 108, Tổ 20 — 108
4135	c59288c0	AGV01	go_to	108	completed	2026-07-16 14:44:59.54306+07	2026-07-16 14:52:47.941475+07	2026-07-16 14:52:47.943471+07	already_at_dest	bjr97bjdsef6	Mobile → Tổ 20 — 108, Tổ 20 — 108
4202	8cf3bc95	AGV02	go_charge	\N	cancelled	2026-07-17 15:10:33.726409+07	\N	2026-07-17 15:10:39.963684+07	cancelled by user	iqkgd38cx64r	Mobile → Tổ 22 — 101, Tổ 22 — 101
4136	e049f0fc	AGV01	go_charge	\N	completed	2026-07-16 14:44:59.54306+07	2026-07-16 14:52:47.94694+07	2026-07-16 14:54:53.1829+07	off_route	bjr97bjdsef6	Mobile → Tổ 20 — 108, Tổ 20 — 108
4139	a07367de	AGV01	go_charge	\N	cancelled	2026-07-16 15:01:31.945829+07	2026-07-16 15:01:53.494609+07	2026-07-16 15:02:18.457095+07	force-cancelled by user	\N	hmi_station_trigger
4182	05714c87	AGV02	go_charge	\N	cancelled	2026-07-17 11:51:58.43856+07	\N	2026-07-17 11:57:04.659388+07	cancelled by user	fz6gy2tme3k7	Mobile → Tổ 22 — 101, Tổ 22 — 101
4180	08c8efa9	AGV02	go_to	101	cancelled	2026-07-17 11:51:58.43856+07	\N	2026-07-17 11:57:04.659388+07	cancelled by user	fz6gy2tme3k7	Mobile → Tổ 22 — 101, Tổ 22 — 101
4181	9e2ef0f8	AGV02	go_to	101	cancelled	2026-07-17 11:51:58.43756+07	\N	2026-07-17 11:57:04.659388+07	cancelled by user	fz6gy2tme3k7	Mobile → Tổ 22 — 101, Tổ 22 — 101
4185	204ede73	AGV02	go_to	102	cancelled	2026-07-17 11:58:07.570302+07	\N	2026-07-17 11:58:38.429476+07	cancelled by user	9ppvimtkey12	Mobile → Tổ 23 — 102, Tổ 23 — 102
4184	339ad529	AGV02	go_to	102	cancelled	2026-07-17 11:58:07.5713+07	\N	2026-07-17 11:58:38.429476+07	cancelled by user	9ppvimtkey12	Mobile → Tổ 23 — 102, Tổ 23 — 102
4186	434fed87	AGV02	go_charge	\N	cancelled	2026-07-17 11:58:07.5713+07	\N	2026-07-17 11:58:38.429476+07	cancelled by user	9ppvimtkey12	Mobile → Tổ 23 — 102, Tổ 23 — 102
4188	1ec6ee39	AGV02	go_to	101	cancelled	2026-07-17 15:03:53.455983+07	\N	2026-07-17 15:04:23.47306+07	cancelled by user	i3c9t1ua7joj	Mobile → Tổ 22 — 101, Tổ 22 — 101
4187	1006c33b	AGV02	go_to	82	cancelled	2026-07-17 15:03:53.153138+07	2026-07-17 15:03:53.153138+07	2026-07-17 15:04:23.47306+07	force-cancelled by user	i3c9t1ua7joj	Mobile → Tổ 22 — 101, Tổ 22 — 101
4189	5a467ada	AGV02	go_to	101	cancelled	2026-07-17 15:03:53.458074+07	\N	2026-07-17 15:04:23.47306+07	cancelled by user	i3c9t1ua7joj	Mobile → Tổ 22 — 101, Tổ 22 — 101
4190	bc61b65c	AGV02	go_charge	\N	cancelled	2026-07-17 15:03:53.45905+07	\N	2026-07-17 15:04:23.47306+07	cancelled by user	i3c9t1ua7joj	Mobile → Tổ 22 — 101, Tổ 22 — 101
4191	e713e5ed	AGV02	go_to	82	cancelled	2026-07-17 15:07:41.9933+07	2026-07-17 15:07:41.9933+07	2026-07-17 15:07:46.489307+07	force-cancelled by user	jt2ynndx4q1p	Mobile → Tổ 22 — 101, Tổ 22 — 101
4192	ae56b612	AGV02	go_to	101	cancelled	2026-07-17 15:07:42.004304+07	\N	2026-07-17 15:07:46.489307+07	cancelled by user	jt2ynndx4q1p	Mobile → Tổ 22 — 101, Tổ 22 — 101
4193	837e4297	AGV02	go_to	101	cancelled	2026-07-17 15:07:42.005304+07	\N	2026-07-17 15:07:46.489307+07	cancelled by user	jt2ynndx4q1p	Mobile → Tổ 22 — 101, Tổ 22 — 101
4194	68ed4ed4	AGV02	go_charge	\N	cancelled	2026-07-17 15:07:42.005304+07	\N	2026-07-17 15:07:46.489307+07	cancelled by user	jt2ynndx4q1p	Mobile → Tổ 22 — 101, Tổ 22 — 101
4195	488cd99a	AGV02	go_to	82	cancelled	2026-07-17 15:08:27.839783+07	2026-07-17 15:08:27.839783+07	2026-07-17 15:08:42.365233+07	force-cancelled by user	ubtma9hjq3h4	Mobile → Tổ 22 — 101, Tổ 22 — 101
4196	40e04c61	AGV02	go_to	101	cancelled	2026-07-17 15:08:27.845783+07	\N	2026-07-17 15:08:42.365233+07	cancelled by user	ubtma9hjq3h4	Mobile → Tổ 22 — 101, Tổ 22 — 101
4197	3158446c	AGV02	go_to	101	cancelled	2026-07-17 15:08:27.845783+07	\N	2026-07-17 15:08:42.365233+07	cancelled by user	ubtma9hjq3h4	Mobile → Tổ 22 — 101, Tổ 22 — 101
4198	c0202fa0	AGV02	go_charge	\N	cancelled	2026-07-17 15:08:27.846784+07	\N	2026-07-17 15:08:42.365233+07	cancelled by user	ubtma9hjq3h4	Mobile → Tổ 22 — 101, Tổ 22 — 101
4200	54197424	AGV02	go_to	101	cancelled	2026-07-17 15:10:33.725409+07	\N	2026-07-17 15:10:39.963684+07	cancelled by user	iqkgd38cx64r	Mobile → Tổ 22 — 101, Tổ 22 — 101
4199	082567ab	AGV02	go_to	82	cancelled	2026-07-17 15:10:33.711409+07	2026-07-17 15:10:33.711409+07	2026-07-17 15:10:39.963684+07	force-cancelled by user	iqkgd38cx64r	Mobile → Tổ 22 — 101, Tổ 22 — 101
4201	2b596a51	AGV02	go_to	101	cancelled	2026-07-17 15:10:33.725409+07	\N	2026-07-17 15:10:39.963684+07	cancelled by user	iqkgd38cx64r	Mobile → Tổ 22 — 101, Tổ 22 — 101
4204	e504b411	AGV02	go_to	101	cancelled	2026-07-17 15:43:38.982021+07	\N	2026-07-17 15:44:43.013398+07	cancelled by user	0tpch2rl46ui	Mobile → Tổ 22 — 101, Tổ 22 — 101
4203	599aded0	AGV02	go_to	82	cancelled	2026-07-17 15:43:38.806835+07	2026-07-17 15:43:38.806835+07	2026-07-17 15:44:43.013398+07	force-cancelled by user	0tpch2rl46ui	Mobile → Tổ 22 — 101, Tổ 22 — 101
4205	5fede1fc	AGV02	go_to	101	cancelled	2026-07-17 15:43:38.983346+07	\N	2026-07-17 15:44:43.013398+07	cancelled by user	0tpch2rl46ui	Mobile → Tổ 22 — 101, Tổ 22 — 101
4206	06b5697b	AGV02	go_charge	\N	cancelled	2026-07-17 15:43:38.983855+07	\N	2026-07-17 15:44:43.013398+07	cancelled by user	0tpch2rl46ui	Mobile → Tổ 22 — 101, Tổ 22 — 101
4207	fae5da75	AGV02	go_to	82	cancelled	2026-07-17 15:45:05.575389+07	2026-07-17 15:45:05.575389+07	2026-07-17 15:45:18.965833+07	force-cancelled by user	ejl7ujur0mih	Mobile → Tổ 22 — 101, Tổ 22 — 101
4209	12b51c5b	AGV02	go_to	101	cancelled	2026-07-17 15:45:05.596544+07	\N	2026-07-17 15:45:18.965833+07	cancelled by user	ejl7ujur0mih	Mobile → Tổ 22 — 101, Tổ 22 — 101
4208	f77a2892	AGV02	go_to	101	cancelled	2026-07-17 15:45:05.596544+07	\N	2026-07-17 15:45:18.965833+07	cancelled by user	ejl7ujur0mih	Mobile → Tổ 22 — 101, Tổ 22 — 101
4210	92b40e23	AGV02	go_charge	\N	cancelled	2026-07-17 15:45:05.597444+07	\N	2026-07-17 15:45:18.965833+07	cancelled by user	ejl7ujur0mih	Mobile → Tổ 22 — 101, Tổ 22 — 101
4211	99534350	AGV02	go_to	82	cancelled	2026-07-17 15:45:41.011283+07	2026-07-17 15:45:41.011283+07	2026-07-17 15:46:00.329881+07	force-cancelled by user	52gno08qa9zn	Mobile → Tổ 22 — 101, Tổ 22 — 101
4212	92da8fd8	AGV02	go_to	101	cancelled	2026-07-17 15:45:41.021283+07	\N	2026-07-17 15:46:00.329881+07	cancelled by user	52gno08qa9zn	Mobile → Tổ 22 — 101, Tổ 22 — 101
4213	1a3bb013	AGV02	go_to	101	cancelled	2026-07-17 15:45:41.021283+07	\N	2026-07-17 15:46:00.329881+07	cancelled by user	52gno08qa9zn	Mobile → Tổ 22 — 101, Tổ 22 — 101
4214	1dc48d53	AGV02	go_charge	\N	cancelled	2026-07-17 15:45:41.022288+07	\N	2026-07-17 15:46:00.329881+07	cancelled by user	52gno08qa9zn	Mobile → Tổ 22 — 101, Tổ 22 — 101
4215	b6bcd9f2	AGV02	go_to	82	cancelled	2026-07-17 15:58:41.939057+07	2026-07-17 15:58:41.939057+07	2026-07-17 16:00:28.456521+07	force-cancelled by user	pxvhw7g70bfc	Mobile → Tổ 23 — 102, Tổ 23 — 102
4217	0fdcbf28	AGV02	go_to	102	cancelled	2026-07-17 15:58:42.089333+07	\N	2026-07-17 16:00:28.457524+07	cancelled by user	pxvhw7g70bfc	Mobile → Tổ 23 — 102, Tổ 23 — 102
4216	d34c241d	AGV02	go_to	102	cancelled	2026-07-17 15:58:42.091332+07	\N	2026-07-17 16:00:28.457524+07	cancelled by user	pxvhw7g70bfc	Mobile → Tổ 23 — 102, Tổ 23 — 102
4218	acbe9f21	AGV02	go_charge	\N	cancelled	2026-07-17 15:58:42.092326+07	\N	2026-07-17 16:00:28.457524+07	cancelled by user	pxvhw7g70bfc	Mobile → Tổ 23 — 102, Tổ 23 — 102
4219	654cf649	AGV02	go_to	82	cancelled	2026-07-17 16:26:51.664116+07	2026-07-17 16:26:51.664116+07	2026-07-17 16:27:23.162319+07	force-cancelled by user	l7c5suo44ajt	Mobile → Tổ 22 — 101, Tổ 22 — 101
4220	9e6c6b8b	AGV02	go_to	101	cancelled	2026-07-17 16:26:51.906117+07	\N	2026-07-17 16:27:23.162319+07	cancelled by user	l7c5suo44ajt	Mobile → Tổ 22 — 101, Tổ 22 — 101
4221	373d509b	AGV02	go_to	101	cancelled	2026-07-17 16:26:51.907338+07	\N	2026-07-17 16:27:23.162319+07	cancelled by user	l7c5suo44ajt	Mobile → Tổ 22 — 101, Tổ 22 — 101
4222	917017f2	AGV02	go_charge	\N	cancelled	2026-07-17 16:26:51.909365+07	\N	2026-07-17 16:27:23.162319+07	cancelled by user	l7c5suo44ajt	Mobile → Tổ 22 — 101, Tổ 22 — 101
4124	411aaf82	AGV01	go_to	111	cancelled	2026-07-16 14:41:41.280271+07	\N	2026-07-16 14:42:44.735674+07	cancelled by user	qrsevee7f8qg	Mobile → Tổ 19 — 111, Tổ 19 — 111
4126	0cce07a6	AGV01	go_charge	\N	completed	2026-07-16 14:43:26.726516+07	2026-07-16 14:43:26.726516+07	2026-07-16 14:43:29.689112+07	charge_arrived	\N	hmi_station_trigger
4129	5020e469	AGV01	go_to	82	cancelled	2026-07-16 14:44:33.993245+07	\N	2026-07-16 14:44:46.381459+07	cancelled by user	c4git4yvrxo3	Mobile → Tổ 20 — 108, Tổ 20 — 108
4128	0654a930	AGV01	go_charge	\N	cancelled	2026-07-16 14:43:49.345184+07	2026-07-16 14:43:49.345184+07	2026-07-16 14:44:46.381459+07	force-cancelled by user	\N	hmi_station_trigger
4133	980ff01e	AGV01	go_to	82	completed	2026-07-16 14:44:59.53306+07	2026-07-16 14:44:59.53306+07	2026-07-16 14:50:24.511646+07	event:continue	bjr97bjdsef6	Mobile → Tổ 20 — 108, Tổ 20 — 108
4160	537eac6f	AGV02	go_to	102	cancelled	2026-07-17 11:22:21.76483+07	\N	2026-07-17 11:22:42.021909+07	cancelled by user	90l1apqlruie	Mobile → Tổ 23 — 102, Tổ 23 — 102
4134	e984c9b6	AGV01	go_to	108	completed	2026-07-16 14:44:59.542058+07	2026-07-16 14:50:24.511646+07	2026-07-16 14:52:47.940475+07	hook_raised	bjr97bjdsef6	Mobile → Tổ 20 — 108, Tổ 20 — 108
4137	7696cd98	AGV01	go_charge	10	completed	2026-07-16 14:54:53.1829+07	2026-07-16 14:54:53.183895+07	2026-07-16 14:55:40.52974+07	off_route	bjr97bjdsef6	Mobile → Tổ 20 — 108, Tổ 20 — 108
4138	f0f7a9b3	AGV01	go_charge	10	completed	2026-07-16 14:55:40.52974+07	2026-07-16 14:55:40.53074+07	2026-07-16 15:01:53.494609+07	lifecycle:picking:confirmed	bjr97bjdsef6	Mobile → Tổ 20 — 108, Tổ 20 — 108
4140	ea1039f1	AGV01	go_to	82	cancelled	2026-07-16 16:09:49.111775+07	2026-07-16 16:09:49.111775+07	2026-07-16 16:10:30.270073+07	force-cancelled by user	mrnafsetbbssw43er1t	Sạc Pin
4141	32f0f59f	AGV01	go_charge	\N	cancelled	2026-07-16 16:09:49.165312+07	\N	2026-07-16 16:10:30.290811+07	cancelled by user	mrnafsetbbssw43er1t	Sạc Pin
4142	3518c235	AGV01	go_charge	\N	completed	2026-07-16 16:10:37.233317+07	2026-07-16 16:10:37.233317+07	2026-07-16 16:10:55.935424+07	off_route	\N	hmi_station_trigger
4162	443548c8	AGV02	go_charge	\N	cancelled	2026-07-17 11:22:21.76583+07	\N	2026-07-17 11:22:42.021909+07	cancelled by user	90l1apqlruie	Mobile → Tổ 23 — 102, Tổ 23 — 102
4144	6cec07d7	AGV01	go_charge	\N	cancelled	2026-07-16 16:10:56.330748+07	\N	2026-07-16 16:10:57.457971+07	cancelled by user	\N	hmi_station_trigger
4143	f61e529a	AGV01	go_charge	10	cancelled	2026-07-16 16:10:55.933405+07	2026-07-16 16:10:55.935424+07	2026-07-16 16:10:57.456971+07	force-cancelled by user	\N	hmi_station_trigger
4145	c39b2156	AGV01	go_to	82	failed	2026-07-16 16:11:18.086932+07	2026-07-16 16:11:18.086932+07	2026-07-16 16:11:18.126432+07	dispatch failed	mrnahp39ee5hpmm2t6t	Sạc Pin
4146	5095487e	AGV01	go_charge	\N	completed	2026-07-16 16:11:18.142887+07	2026-07-16 16:11:18.142887+07	2026-07-16 16:11:19.699006+07	charge_arrived	mrnahp39ee5hpmm2t6t	Sạc Pin
4147	01760eed	AGV01	go_to	82	cancelled	2026-07-16 16:12:42.561152+07	2026-07-16 16:12:42.561152+07	2026-07-16 16:13:22.847476+07	force-cancelled by user	ccm2rq6a6xbh	Mobile → Tổ 22 — 101, Tổ 22 — 101
4148	64125c47	AGV01	go_to	101	cancelled	2026-07-16 16:12:42.635152+07	\N	2026-07-16 16:13:22.848472+07	cancelled by user	ccm2rq6a6xbh	Mobile → Tổ 22 — 101, Tổ 22 — 101
4149	5a62da14	AGV01	go_to	101	cancelled	2026-07-16 16:12:42.639148+07	\N	2026-07-16 16:13:22.848472+07	cancelled by user	ccm2rq6a6xbh	Mobile → Tổ 22 — 101, Tổ 22 — 101
4150	eec940c2	AGV01	go_charge	\N	cancelled	2026-07-16 16:12:42.643151+07	\N	2026-07-16 16:13:22.848472+07	cancelled by user	ccm2rq6a6xbh	Mobile → Tổ 22 — 101, Tổ 22 — 101
4152	26538e8a	AGV02	go_to	101	cancelled	2026-07-17 10:00:42.5921+07	\N	2026-07-17 10:00:52.929406+07	cancelled by user	1attwsu7jvxr	Mobile → Tổ 22 — 101, Tổ 22 — 101
4151	b294f50f	AGV02	go_to	82	cancelled	2026-07-17 10:00:42.541096+07	2026-07-17 10:00:42.541096+07	2026-07-17 10:00:52.929406+07	force-cancelled by user	1attwsu7jvxr	Mobile → Tổ 22 — 101, Tổ 22 — 101
4153	3035221a	AGV02	go_to	101	cancelled	2026-07-17 10:00:42.593098+07	\N	2026-07-17 10:00:52.929406+07	cancelled by user	1attwsu7jvxr	Mobile → Tổ 22 — 101, Tổ 22 — 101
4154	06f476ee	AGV02	go_charge	\N	cancelled	2026-07-17 10:00:42.5951+07	\N	2026-07-17 10:00:52.929406+07	cancelled by user	1attwsu7jvxr	Mobile → Tổ 22 — 101, Tổ 22 — 101
4155	76018fbb	AGV02	go_to	82	running	2026-07-17 10:44:51.934647+07	\N	\N	\N	afnqqfywwd5o	Mobile → Tổ 22 — 101, Tổ 22 — 101
4156	c09d3235	AGV02	go_to	101	queued	2026-07-17 10:44:52.010645+07	\N	\N	\N	afnqqfywwd5o	Mobile → Tổ 22 — 101, Tổ 22 — 101
4157	1567ba2a	AGV02	go_to	101	queued	2026-07-17 10:44:52.010645+07	\N	\N	\N	afnqqfywwd5o	Mobile → Tổ 22 — 101, Tổ 22 — 101
4158	5b940ed5	AGV02	go_charge	\N	queued	2026-07-17 10:44:52.011646+07	\N	\N	\N	afnqqfywwd5o	Mobile → Tổ 22 — 101, Tổ 22 — 101
4161	a7152511	AGV02	go_to	102	cancelled	2026-07-17 11:22:21.76483+07	\N	2026-07-17 11:22:42.021909+07	cancelled by user	90l1apqlruie	Mobile → Tổ 23 — 102, Tổ 23 — 102
4159	dd7c41ff	AGV02	go_to	82	cancelled	2026-07-17 11:22:21.536969+07	2026-07-17 11:22:21.536969+07	2026-07-17 11:22:42.021909+07	force-cancelled by user	90l1apqlruie	Mobile → Tổ 23 — 102, Tổ 23 — 102
4163	11ac7d1b	AGV02	go_to	82	cancelled	2026-07-17 11:23:23.626524+07	2026-07-17 11:23:23.626524+07	2026-07-17 11:28:59.666587+07	force-cancelled by user	829z295lkvrw	Mobile → Tổ 23 — 102, Tổ 23 — 102
4165	19b1558f	AGV02	go_to	102	cancelled	2026-07-17 11:23:23.701231+07	\N	2026-07-17 11:28:59.666587+07	cancelled by user	829z295lkvrw	Mobile → Tổ 23 — 102, Tổ 23 — 102
4164	fbcd1d9d	AGV02	go_to	102	cancelled	2026-07-17 11:23:23.702228+07	\N	2026-07-17 11:28:59.666587+07	cancelled by user	829z295lkvrw	Mobile → Tổ 23 — 102, Tổ 23 — 102
4166	54ec7595	AGV02	go_charge	\N	cancelled	2026-07-17 11:23:23.702228+07	\N	2026-07-17 11:28:59.666587+07	cancelled by user	829z295lkvrw	Mobile → Tổ 23 — 102, Tổ 23 — 102
4167	5d73581e	AGV02	go_to	82	cancelled	2026-07-17 11:29:09.953044+07	2026-07-17 11:29:09.953044+07	2026-07-17 11:32:52.78639+07	force-cancelled by user	inzlqdvl9nfv	Mobile → Tổ 22 — 101, Tổ 22 — 101
4169	9abd8053	AGV02	go_to	101	cancelled	2026-07-17 11:29:09.986936+07	\N	2026-07-17 11:32:52.78639+07	cancelled by user	inzlqdvl9nfv	Mobile → Tổ 22 — 101, Tổ 22 — 101
4168	e52bfe7a	AGV02	go_to	101	cancelled	2026-07-17 11:29:09.987955+07	\N	2026-07-17 11:32:52.78639+07	cancelled by user	inzlqdvl9nfv	Mobile → Tổ 22 — 101, Tổ 22 — 101
4170	af8abd9d	AGV02	go_charge	\N	cancelled	2026-07-17 11:29:09.988982+07	\N	2026-07-17 11:32:52.78639+07	cancelled by user	inzlqdvl9nfv	Mobile → Tổ 22 — 101, Tổ 22 — 101
4172	ffeb8f13	AGV02	go_to	101	cancelled	2026-07-17 11:33:02.318657+07	\N	2026-07-17 11:34:01.824585+07	cancelled by user	p0bt5rcz3lt9	Mobile → Tổ 22 — 101, Tổ 22 — 101
4171	ef2d322b	AGV02	go_to	82	cancelled	2026-07-17 11:33:02.297614+07	2026-07-17 11:33:02.297614+07	2026-07-17 11:34:01.824585+07	force-cancelled by user	p0bt5rcz3lt9	Mobile → Tổ 22 — 101, Tổ 22 — 101
4173	91a7bc74	AGV02	go_to	101	cancelled	2026-07-17 11:33:02.320644+07	\N	2026-07-17 11:34:01.824585+07	cancelled by user	p0bt5rcz3lt9	Mobile → Tổ 22 — 101, Tổ 22 — 101
4174	30284fd2	AGV02	go_charge	\N	cancelled	2026-07-17 11:33:02.321644+07	\N	2026-07-17 11:34:01.824585+07	cancelled by user	p0bt5rcz3lt9	Mobile → Tổ 22 — 101, Tổ 22 — 101
4175	1bf0d90d	AGV02	go_to	82	cancelled	2026-07-17 11:36:06.545971+07	2026-07-17 11:36:06.545971+07	2026-07-17 11:36:26.445171+07	force-cancelled by user	h4ozrivbuoue	Mobile → Tổ 23 — 102, Tổ 23 — 102
4176	d6ec8b4c	AGV02	go_to	102	cancelled	2026-07-17 11:36:06.557175+07	\N	2026-07-17 11:36:26.445171+07	cancelled by user	h4ozrivbuoue	Mobile → Tổ 23 — 102, Tổ 23 — 102
4178	8e778764	AGV02	go_charge	\N	cancelled	2026-07-17 11:36:06.557175+07	\N	2026-07-17 11:36:26.445171+07	cancelled by user	h4ozrivbuoue	Mobile → Tổ 23 — 102, Tổ 23 — 102
4177	a532fde0	AGV02	go_to	102	cancelled	2026-07-17 11:36:06.557175+07	\N	2026-07-17 11:36:26.445171+07	cancelled by user	h4ozrivbuoue	Mobile → Tổ 23 — 102, Tổ 23 — 102
4179	8b5630f9	AGV02	go_to	82	cancelled	2026-07-17 11:51:58.363903+07	2026-07-17 11:51:58.363903+07	2026-07-17 11:57:04.658328+07	force-cancelled by user	fz6gy2tme3k7	Mobile → Tổ 22 — 101, Tổ 22 — 101
4183	0220022b	AGV02	go_to	82	cancelled	2026-07-17 11:58:07.553307+07	2026-07-17 11:58:07.553307+07	2026-07-17 11:58:38.429476+07	force-cancelled by user	9ppvimtkey12	Mobile → Tổ 23 — 102, Tổ 23 — 102
4223	5788c980	AGV02	go_to	82	cancelled	2026-07-17 16:27:53.38263+07	2026-07-17 16:27:53.38263+07	2026-07-17 16:28:20.672912+07	force-cancelled by user	0vozuk7wn20j	Mobile → Tổ 22 — 101, Tổ 22 — 101
4225	c163b0e1	AGV02	go_to	101	cancelled	2026-07-17 16:27:53.446457+07	\N	2026-07-17 16:28:20.672912+07	cancelled by user	0vozuk7wn20j	Mobile → Tổ 22 — 101, Tổ 22 — 101
4226	499a82f3	AGV02	go_charge	\N	cancelled	2026-07-17 16:27:53.447458+07	\N	2026-07-17 16:28:20.672912+07	cancelled by user	0vozuk7wn20j	Mobile → Tổ 22 — 101, Tổ 22 — 101
4224	3e97d87f	AGV02	go_to	101	cancelled	2026-07-17 16:27:53.447458+07	\N	2026-07-17 16:28:20.672912+07	cancelled by user	0vozuk7wn20j	Mobile → Tổ 22 — 101, Tổ 22 — 101
4227	314a7848	AGV02	go_to	82	completed	2026-07-17 16:28:26.687744+07	2026-07-17 16:28:26.687744+07	2026-07-17 16:32:45.89555+07	event:continue	vwd4z832barf	Mobile → Tổ 22 — 101, Tổ 22 — 101
4243	5a1a6037	AGV02	go_to	102	failed	2026-07-17 16:55:07.829548+07	2026-07-17 16:57:06.542909+07	2026-07-17 16:57:06.59847+07	auto-dispatch failed	wzwhdljm6wmj	Mobile → Tổ 23 — 102, Tổ 23 — 102
4228	8bf3902e	AGV02	go_to	101	completed	2026-07-17 16:28:26.705747+07	2026-07-17 16:32:45.89555+07	2026-07-17 16:33:04.504493+07	off_route	vwd4z832barf	Mobile → Tổ 22 — 101, Tổ 22 — 101
4231	a3d92c3d	AGV02	go_to	101	completed	2026-07-17 16:33:04.504493+07	2026-07-17 16:33:04.50649+07	2026-07-17 16:33:37.814526+07	hook_raised	vwd4z832barf	Mobile → Tổ 22 — 101, Tổ 22 — 101
4244	97bc606a	AGV02	go_charge	\N	cancelled	2026-07-17 16:55:07.834546+07	\N	2026-07-17 16:57:10.93378+07	cancelled by user	wzwhdljm6wmj	Mobile → Tổ 23 — 102, Tổ 23 — 102
4229	9d7e023b	AGV02	go_to	101	completed	2026-07-17 16:28:26.705747+07	2026-07-17 16:33:37.815525+07	2026-07-17 16:33:37.818575+07	already_at_dest	vwd4z832barf	Mobile → Tổ 22 — 101, Tổ 22 — 101
4230	50cf323f	AGV02	go_charge	\N	completed	2026-07-17 16:28:26.706747+07	2026-07-17 16:33:37.818575+07	2026-07-17 16:34:23.486751+07	off_route	vwd4z832barf	Mobile → Tổ 22 — 101, Tổ 22 — 101
4232	be24eeec	AGV02	go_charge	10	cancelled	2026-07-17 16:34:23.484739+07	2026-07-17 16:34:23.487757+07	2026-07-17 16:37:36.613501+07	force-cancelled by user	vwd4z832barf	Mobile → Tổ 22 — 101, Tổ 22 — 101
4233	adcf504d	AGV02	go_to	82	completed	2026-07-17 16:38:11.523941+07	2026-07-17 16:38:11.523941+07	2026-07-17 16:39:19.44934+07	event:continue	9wy9yr2l3dx8	Mobile → Tổ 22 — 101, Tổ 22 — 101
4234	5819a823	AGV02	go_to	101	completed	2026-07-17 16:38:11.554376+07	2026-07-17 16:39:19.450342+07	2026-07-17 16:40:20.328961+07	hook_raised	9wy9yr2l3dx8	Mobile → Tổ 22 — 101, Tổ 22 — 101
4235	de48ccee	AGV02	go_to	101	completed	2026-07-17 16:38:11.55775+07	2026-07-17 16:40:20.328961+07	2026-07-17 16:40:20.331963+07	already_at_dest	9wy9yr2l3dx8	Mobile → Tổ 22 — 101, Tổ 22 — 101
4245	741e7931	AGV02	go_to	101	completed	2026-07-17 16:57:52.446256+07	2026-07-17 16:57:52.446256+07	2026-07-17 16:59:09.502529+07	event:continue	c42dzwgswydf	Mobile → Tổ 22 — 101, Tổ 22 — 101
4236	e8477f6d	AGV02	go_charge	\N	completed	2026-07-17 16:38:11.558753+07	2026-07-17 16:40:20.331963+07	2026-07-17 16:41:01.12856+07	off_route	9wy9yr2l3dx8	Mobile → Tổ 22 — 101, Tổ 22 — 101
4237	a27c8a53	AGV02	go_charge	10	queued	2026-07-17 16:41:01.127555+07	\N	\N	\N	9wy9yr2l3dx8	Mobile → Tổ 22 — 101, Tổ 22 — 101
4238	d4454662	AGV02	go_to	82	cancelled	2026-07-17 16:52:28.495259+07	2026-07-17 16:52:28.495259+07	2026-07-17 16:52:36.90086+07	force-cancelled by user	mrorehwn4zbvycju3l6	Sạc Pin
4239	cb34e9fc	AGV02	go_charge	\N	cancelled	2026-07-17 16:52:28.864603+07	\N	2026-07-17 16:52:36.903868+07	cancelled by user	mrorehwn4zbvycju3l6	Sạc Pin
4240	3df332a7	AGV02	go_to	82	completed	2026-07-17 16:53:15.925944+07	2026-07-17 16:53:15.925944+07	2026-07-17 16:54:01.804159+07	event:continue	mrorfiix1hfk3h5bram	Sạc Pin
4255	70c340e2	AGV02	go_charge	\N	completed	2026-07-18 08:49:39.282641+07	2026-07-18 08:49:39.282641+07	2026-07-18 08:49:56.725455+07	charge_arrived	mrpplfif8sop2t1u9m	Sạc Pin
4241	74af8521	AGV02	go_charge	\N	cancelled	2026-07-17 16:53:15.964333+07	2026-07-17 16:54:01.805152+07	2026-07-17 16:54:34.094896+07	force-cancelled by user	mrorfiix1hfk3h5bram	Sạc Pin
4242	62d8415e	AGV02	go_to	102	completed	2026-07-17 16:55:07.763972+07	2026-07-17 16:55:07.763972+07	2026-07-17 16:57:06.542909+07	lifecycle:picking:confirmed	wzwhdljm6wmj	Mobile → Tổ 23 — 102, Tổ 23 — 102
4246	1b928f7c	AGV02	go_to	101	running	2026-07-17 16:57:52.490941+07	2026-07-17 16:59:09.50453+07	\N		c42dzwgswydf	Mobile → Tổ 22 — 101, Tổ 22 — 101
4247	5c186e93	AGV02	go_charge	\N	cancelled	2026-07-17 16:57:52.496941+07	2026-07-17 16:59:09.512529+07	2026-07-17 17:01:39.509979+07	force-cancelled by user	c42dzwgswydf	Mobile → Tổ 22 — 101, Tổ 22 — 101
4259	036956ed	AGV02	go_to	103	queued	2026-07-18 08:50:53.421105+07	\N	\N	\N	qcaum36niq6m	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103, Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103
4252	bd16aeeb	AGV02	go_to	82	completed	2026-07-18 08:35:38.088977+07	2026-07-18 08:35:38.088977+07	2026-07-18 08:36:33.494721+07	event:continue	\N	\N
4260	3ff2b8cf	AGV02	go_to	101	queued	2026-07-18 08:50:53.428106+07	\N	\N	\N	qcaum36niq6m	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103, Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103
4251	e4e703a1	AGV02	go_to	101	completed	2026-07-18 08:35:38.088977+07	2026-07-18 08:36:33.496723+07	2026-07-18 08:37:19.461804+07	hook_raised	\N	\N
4250	0ed9cf7b	AGV02	go_to	201	completed	2026-07-18 08:35:38.088977+07	2026-07-18 08:37:19.463802+07	2026-07-18 08:38:23.110303+07	event:continue	\N	\N
4261	52b59263	AGV02	go_to	102	queued	2026-07-18 08:50:53.434116+07	\N	\N	\N	qcaum36niq6m	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103, Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103
4262	d5b25379	AGV02	go_to	103	queued	2026-07-18 08:50:53.438106+07	\N	\N	\N	qcaum36niq6m	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103, Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103
4249	57ccf552	AGV02	go_to	81	completed	2026-07-18 08:35:38.088977+07	2026-07-18 08:38:23.111298+07	2026-07-18 08:39:13.773236+07	hook_raised	\N	\N
4248	ebcb2581	AGV02	go_charge	\N	completed	2026-07-18 08:35:38.087978+07	2026-07-18 08:39:13.775053+07	2026-07-18 08:41:29.37168+07	lifecycle:picking:confirmed	\N	\N
4253	fc38fb58	AGV02	go_charge	\N	cancelled	2026-07-18 08:48:50.794779+07	2026-07-18 08:48:50.794779+07	2026-07-18 08:49:17.443993+07	force-cancelled by user	mrppkee0kc0rbnqyqj	Sạc Pin
4254	06a5258e	AGV02	go_to	82	failed	2026-07-18 08:49:39.025813+07	2026-07-18 08:49:39.025813+07	2026-07-18 08:49:39.266641+07	dispatch failed	mrpplfif8sop2t1u9m	Sạc Pin
4263	9a25f6c9	AGV02	go_charge	\N	queued	2026-07-18 08:50:53.441102+07	\N	\N	\N	qcaum36niq6m	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103, Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103
4256	360b7b51	AGV02	go_to	82	completed	2026-07-18 08:50:53.34685+07	2026-07-18 08:50:53.34685+07	2026-07-18 08:51:52.787097+07	event:continue	qcaum36niq6m	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103, Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103
4258	6d057597	AGV02	go_to	102	completed	2026-07-18 08:50:53.417117+07	2026-07-18 08:52:36.612572+07	2026-07-18 08:52:42.506922+07	off_route	qcaum36niq6m	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103, Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103
4257	22792a06	AGV02	go_to	101	completed	2026-07-18 08:50:53.415105+07	2026-07-18 08:51:52.787097+07	2026-07-18 08:52:36.610573+07	hook_raised	qcaum36niq6m	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103, Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103
4266	1512cee6	AGV02	go_to	82	completed	2026-07-18 09:18:25.124906+07	2026-07-18 09:18:25.124906+07	2026-07-18 09:19:10.043358+07	event:continue	yei69enxbtfq	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4264	83097336	AGV02	go_to	102	completed	2026-07-18 08:52:42.505913+07	2026-07-18 08:52:42.50892+07	2026-07-18 08:53:49.709654+07	off_route	qcaum36niq6m	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103, Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103
4265	2297c243	AGV02	go_to	102	failed	2026-07-18 08:53:49.708656+07	2026-07-18 08:53:49.710652+07	2026-07-18 08:53:49.784654+07	auto-dispatch failed	qcaum36niq6m	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103, Tổ 22 — 101, Tổ 23 — 102, Tổ 24 — 103
4268	6a853e02	AGV02	go_to	101	completed	2026-07-18 09:18:25.291989+07	2026-07-18 09:19:10.044355+07	2026-07-18 09:19:52.135594+07	hook_raised	yei69enxbtfq	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4270	c58a68ac	AGV02	go_to	101	failed	2026-07-18 09:18:25.303538+07	2026-07-18 09:40:30.398985+07	2026-07-18 09:40:30.426006+07	auto-dispatch failed	yei69enxbtfq	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4267	00f218f8	AGV02	go_to	201	completed	2026-07-18 09:18:25.293499+07	2026-07-18 09:19:52.135594+07	2026-07-18 09:20:44.581325+07	event:continue	yei69enxbtfq	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4286	38440d19	AGV02	go_to	82	completed	2026-07-18 09:57:25.339302+07	2026-07-18 09:57:25.339302+07	2026-07-18 09:58:25.454816+07	event:continue	dl0cro3mmvmh	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4272	5641438f	AGV02	go_to	102	completed	2026-07-18 09:18:25.295595+07	2026-07-18 09:20:44.582327+07	2026-07-18 09:21:13.963363+07	off_route	yei69enxbtfq	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4274	382602d5	AGV02	go_to	102	failed	2026-07-18 09:21:13.963363+07	2026-07-18 09:21:13.964363+07	2026-07-18 09:21:13.976468+07	auto-dispatch failed	yei69enxbtfq	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4269	42e9eb23	AGV02	go_to	202	failed	2026-07-18 09:18:25.300511+07	2026-07-18 09:38:46.467356+07	2026-07-18 09:38:46.536103+07	auto-dispatch failed	yei69enxbtfq	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4271	198f2b47	AGV02	go_to	102	cancelled	2026-07-18 09:18:25.304542+07	\N	2026-07-18 09:41:05.261789+07	cancelled by user	yei69enxbtfq	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4273	c98cec25	AGV02	go_charge	\N	cancelled	2026-07-18 09:18:25.306537+07	\N	2026-07-18 09:41:05.261789+07	cancelled by user	yei69enxbtfq	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4275	d13e9f0a	AGV02	go_charge	\N	completed	2026-07-18 09:41:12.660972+07	2026-07-18 09:41:12.660972+07	2026-07-18 09:41:37.685398+07	charge_arrived	mrprfqohq5uajif4teh	Sạc Pin
4276	fac27299	AGV02	go_to	82	completed	2026-07-18 09:45:37.746475+07	2026-07-18 09:45:37.746475+07	2026-07-18 09:46:47.562242+07	event:continue	0kizhb3d3p6y	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4278	b808018a	AGV02	go_to	101	completed	2026-07-18 09:45:37.91751+07	2026-07-18 09:46:47.563145+07	2026-07-18 09:47:36.056128+07	event:continue	0kizhb3d3p6y	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4288	f634a1b6	AGV02	go_to	101	completed	2026-07-18 09:57:25.416303+07	2026-07-18 09:58:25.454816+07	2026-07-18 09:59:10.39312+07	event:continue	dl0cro3mmvmh	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4287	0fe1bdd6	AGV02	go_to	102	completed	2026-07-18 09:57:25.416303+07	2026-07-18 09:59:10.39412+07	2026-07-18 09:59:20.234856+07	hook_raised	dl0cro3mmvmh	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4277	6df706fe	AGV02	go_to	102	completed	2026-07-18 09:45:37.91952+07	2026-07-18 09:47:36.058172+07	2026-07-18 09:47:46.495035+07	hook_raised	0kizhb3d3p6y	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4281	0b7d38fb	AGV02	go_to	101	completed	2026-07-18 09:45:37.921517+07	2026-07-18 09:47:46.495035+07	2026-07-18 09:48:50.921674+07	off_route	0kizhb3d3p6y	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4284	e9b3bddf	AGV02	go_to	101	failed	2026-07-18 09:48:50.920674+07	2026-07-18 09:48:50.922724+07	2026-07-18 09:48:50.932244+07	auto-dispatch failed	0kizhb3d3p6y	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4282	5ec86bee	AGV02	go_to	102	failed	2026-07-18 09:45:37.928519+07	2026-07-18 09:54:05.194637+07	2026-07-18 09:54:05.352686+07	auto-dispatch failed	0kizhb3d3p6y	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4279	06a70ba3	AGV02	go_to	202	cancelled	2026-07-18 09:45:37.935523+07	\N	2026-07-18 09:55:45.7942+07	cancelled by user	0kizhb3d3p6y	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4280	507de506	AGV02	go_to	201	cancelled	2026-07-18 09:45:37.940527+07	\N	2026-07-18 09:55:45.7942+07	cancelled by user	0kizhb3d3p6y	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4283	98cdc5e0	AGV02	go_charge	\N	cancelled	2026-07-18 09:45:37.942529+07	\N	2026-07-18 09:55:45.7942+07	cancelled by user	0kizhb3d3p6y	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4285	719e427d	AGV02	go_charge	\N	completed	2026-07-18 09:56:30.591746+07	2026-07-18 09:56:30.591746+07	2026-07-18 09:56:57.687688+07	charge_arrived	mrprzey76fla0h2d9oo	Sạc Pin
4290	670e7c03	AGV02	go_to	202	completed	2026-07-18 09:57:25.417303+07	2026-07-18 09:59:20.234856+07	2026-07-18 10:00:03.385477+07	event:continue	dl0cro3mmvmh	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4289	669b3baf	AGV02	go_charge	\N	completed	2026-07-18 09:57:25.420305+07	2026-07-18 10:00:10.816993+07	2026-07-18 10:01:07.439641+07	charge_arrived	dl0cro3mmvmh	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4319	f4e59fab	AGV02	go_to	102	cancelled	2026-07-18 10:59:38.282446+07	2026-07-18 10:59:38.282446+07	2026-07-18 10:59:53.558641+07	force-cancelled by user	r9klo45y5pnl	Mobile → Tổ 23 — 102, Tổ 23 — 102
4291	2e2a1b8b	AGV02	go_to	201	completed	2026-07-18 09:57:25.418305+07	2026-07-18 10:00:03.386473+07	2026-07-18 10:00:10.816003+07	event:continue	dl0cro3mmvmh	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4306	94a05678	AGV02	go_charge	\N	completed	2026-07-18 10:25:50.500842+07	2026-07-18 10:29:41.9452+07	2026-07-18 10:30:03.697582+07	charge_arrived	dirs08tugdfc	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4292	8cc8809b	AGV02	go_to	101	completed	2026-07-18 10:09:02.992516+07	2026-07-18 10:09:02.992516+07	2026-07-18 10:10:50.952291+07	event:continue	tpvcb2osktrl	Mobile → Tổ 22 — 101, Tổ 22 — 101
4293	67015702	AGV02	go_to	201	completed	2026-07-18 10:09:03.145938+07	2026-07-18 10:10:50.953294+07	2026-07-18 10:11:46.720168+07	event:continue	tpvcb2osktrl	Mobile → Tổ 22 — 101, Tổ 22 — 101
4294	b41410e1	AGV02	go_charge	\N	completed	2026-07-18 10:09:03.147932+07	2026-07-18 10:11:46.721172+07	2026-07-18 10:12:44.698394+07	charge_arrived	tpvcb2osktrl	Mobile → Tổ 22 — 101, Tổ 22 — 101
4295	a62b0531	AGV02	go_to	82	completed	2026-07-18 10:21:24.708676+07	2026-07-18 10:21:24.708676+07	2026-07-18 10:22:25.028431+07	event:continue	x7p4yflvmfi7	Mobile → Tổ 22 — 101, Tổ 22 — 101
4297	676a2b81	AGV02	go_to	101	completed	2026-07-18 10:21:24.776576+07	2026-07-18 10:22:25.028431+07	2026-07-18 10:23:14.136324+07	hook_raised	x7p4yflvmfi7	Mobile → Tổ 22 — 101, Tổ 22 — 101
4296	95412ca5	AGV02	go_to	201	completed	2026-07-18 10:21:24.777789+07	2026-07-18 10:23:14.137324+07	2026-07-18 10:24:22.52962+07	event:continue	x7p4yflvmfi7	Mobile → Tổ 22 — 101, Tổ 22 — 101
4299	92134c53	AGV02	go_to	81	completed	2026-07-18 10:21:24.778804+07	2026-07-18 10:24:22.52962+07	2026-07-18 10:25:13.686073+07	hook_raised	x7p4yflvmfi7	Mobile → Tổ 22 — 101, Tổ 22 — 101
4309	ecea4b33	AGV02	go_to	201	cancelled	2026-07-18 10:38:37.96815+07	\N	2026-07-18 10:58:09.155097+07	cancelled by user	2v5gbubc8meb	Mobile → Tổ 22 — 101, Tổ 22 — 101
4298	da457052	AGV02	go_charge	\N	completed	2026-07-18 10:21:24.780832+07	2026-07-18 10:25:13.687096+07	2026-07-18 10:25:34.982923+07	charge_arrived	x7p4yflvmfi7	Mobile → Tổ 22 — 101, Tổ 22 — 101
4308	c940ce96	AGV02	go_to	81	cancelled	2026-07-18 10:38:37.969164+07	\N	2026-07-18 10:58:09.155097+07	cancelled by user	2v5gbubc8meb	Mobile → Tổ 22 — 101, Tổ 22 — 101
4300	c9f4de9f	AGV02	go_to	82	completed	2026-07-18 10:25:50.48785+07	2026-07-18 10:25:50.48785+07	2026-07-18 10:26:42.330563+07	event:continue	dirs08tugdfc	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4301	873fc5ff	AGV02	go_to	101	completed	2026-07-18 10:25:50.498843+07	2026-07-18 10:26:42.330563+07	2026-07-18 10:27:23.110024+07	hook_raised	dirs08tugdfc	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4307	d52edcb8	AGV02	go_to	101	cancelled	2026-07-18 10:38:37.825065+07	2026-07-18 10:38:37.825065+07	2026-07-18 10:58:09.154121+07	force-cancelled by user	2v5gbubc8meb	Mobile → Tổ 22 — 101, Tổ 22 — 101
4310	78d1dc97	AGV02	go_charge	\N	cancelled	2026-07-18 10:38:37.970246+07	\N	2026-07-18 10:58:09.155097+07	cancelled by user	2v5gbubc8meb	Mobile → Tổ 22 — 101, Tổ 22 — 101
4302	1a664f4d	AGV02	go_to	102	completed	2026-07-18 10:25:50.498843+07	2026-07-18 10:27:23.11092+07	2026-07-18 10:27:28.690948+07	hook_already_raised	dirs08tugdfc	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4303	7d9f1f3b	AGV02	go_to	202	completed	2026-07-18 10:25:50.499843+07	2026-07-18 10:27:28.69196+07	2026-07-18 10:28:09.525494+07	event:continue	dirs08tugdfc	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4311	1a256d40	AGV02	go_to	101	running	2026-07-18 10:58:14.288564+07	\N	\N	\N	ldvk2sficu9h	Mobile → Tổ 22 — 101, Tổ 22 — 101
4304	4537a9e8	AGV02	go_to	201	completed	2026-07-18 10:25:50.499843+07	2026-07-18 10:28:09.525494+07	2026-07-18 10:28:16.42684+07	event:continue	dirs08tugdfc	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4305	3f41da5e	AGV02	go_to	81	completed	2026-07-18 10:25:50.499843+07	2026-07-18 10:28:16.42684+07	2026-07-18 10:29:41.944197+07	event:continue	dirs08tugdfc	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4312	a4a1a71a	AGV02	go_to	201	cancelled	2026-07-18 10:58:14.291564+07	2026-07-18 10:58:14.291564+07	2026-07-18 10:58:56.212652+07	force-cancelled by user	ldvk2sficu9h	Mobile → Tổ 22 — 101, Tổ 22 — 101
4313	a6c60fae	AGV02	go_to	81	cancelled	2026-07-18 10:58:14.330564+07	\N	2026-07-18 10:58:56.213667+07	cancelled by user	ldvk2sficu9h	Mobile → Tổ 22 — 101, Tổ 22 — 101
4314	2f3e0ffd	AGV02	go_charge	\N	cancelled	2026-07-18 10:58:14.332372+07	\N	2026-07-18 10:58:56.213667+07	cancelled by user	ldvk2sficu9h	Mobile → Tổ 22 — 101, Tổ 22 — 101
4315	f84630e1	AGV02	go_to	101	running	2026-07-18 10:59:00.569844+07	\N	\N	\N	x69c4ydxyiyf	Mobile → Tổ 22 — 101, Tổ 22 — 101
4316	7da96ffb	AGV02	go_to	201	cancelled	2026-07-18 10:59:00.571847+07	2026-07-18 10:59:00.571847+07	2026-07-18 10:59:33.824335+07	force-cancelled by user	x69c4ydxyiyf	Mobile → Tổ 22 — 101, Tổ 22 — 101
4317	26ad1625	AGV02	go_to	81	cancelled	2026-07-18 10:59:00.593839+07	\N	2026-07-18 10:59:33.825335+07	cancelled by user	x69c4ydxyiyf	Mobile → Tổ 22 — 101, Tổ 22 — 101
4318	f0e6e879	AGV02	go_charge	\N	cancelled	2026-07-18 10:59:00.594752+07	\N	2026-07-18 10:59:33.825335+07	cancelled by user	x69c4ydxyiyf	Mobile → Tổ 22 — 101, Tổ 22 — 101
4320	3469d0d1	AGV02	go_to	202	cancelled	2026-07-18 10:59:38.298199+07	\N	2026-07-18 10:59:53.558641+07	cancelled by user	r9klo45y5pnl	Mobile → Tổ 23 — 102, Tổ 23 — 102
4321	0a03a4db	AGV02	go_to	81	cancelled	2026-07-18 10:59:38.2992+07	\N	2026-07-18 10:59:53.558641+07	cancelled by user	r9klo45y5pnl	Mobile → Tổ 23 — 102, Tổ 23 — 102
4322	79d40645	AGV02	go_charge	\N	cancelled	2026-07-18 10:59:38.300201+07	\N	2026-07-18 10:59:53.558641+07	cancelled by user	r9klo45y5pnl	Mobile → Tổ 23 — 102, Tổ 23 — 102
4323	63b80dbe	AGV02	go_to	102	cancelled	2026-07-18 11:00:27.090069+07	2026-07-18 11:00:27.090069+07	2026-07-18 11:00:40.868801+07	force-cancelled by user	7x28t4g176qh	Mobile → Tổ 23 — 102, Tổ 23 — 102
4324	0931a71e	AGV02	go_to	202	cancelled	2026-07-18 11:00:27.10904+07	\N	2026-07-18 11:00:40.868801+07	cancelled by user	7x28t4g176qh	Mobile → Tổ 23 — 102, Tổ 23 — 102
4325	08b608fa	AGV02	go_to	81	cancelled	2026-07-18 11:00:27.110043+07	\N	2026-07-18 11:00:40.868801+07	cancelled by user	7x28t4g176qh	Mobile → Tổ 23 — 102, Tổ 23 — 102
4326	f033f5f2	AGV02	go_charge	\N	cancelled	2026-07-18 11:00:27.112052+07	\N	2026-07-18 11:00:40.868801+07	cancelled by user	7x28t4g176qh	Mobile → Tổ 23 — 102, Tổ 23 — 102
4327	849df97c	AGV02	go_charge	\N	cancelled	2026-07-18 11:01:14.570267+07	2026-07-18 11:01:14.570267+07	2026-07-18 11:01:30.00812+07	force-cancelled by user	mrpuanv4y64dqd2ftw	Sạc Pin
4328	53aabb94	AGV02	go_to	102	completed	2026-07-18 11:03:48.161678+07	2026-07-18 11:03:48.161678+07	2026-07-18 11:05:04.442254+07	event:continue	f91azyfgai47	Mobile → Tổ 23 — 102, Tổ 23 — 102
4330	c38cd373	AGV02	go_to	81	completed	2026-07-18 11:03:48.195572+07	2026-07-18 11:05:50.505746+07	2026-07-18 11:06:31.750079+07	hook_already_raised	f91azyfgai47	Mobile → Tổ 23 — 102, Tổ 23 — 102
4332	84da0d5b	AGV02	go_to	82	completed	2026-07-18 11:07:47.253381+07	2026-07-18 11:07:47.253381+07	2026-07-18 11:08:32.931683+07	event:continue	dpm8sunicfj8	Mobile → Tổ 22 — 101, Tổ 22 — 101
4329	d9cf6454	AGV02	go_to	202	completed	2026-07-18 11:03:48.193564+07	2026-07-18 11:05:04.443252+07	2026-07-18 11:05:50.505746+07	event:continue	f91azyfgai47	Mobile → Tổ 23 — 102, Tổ 23 — 102
4331	69ef660e	AGV02	go_charge	\N	running	2026-07-18 11:03:48.197682+07	2026-07-18 11:06:31.75108+07	\N		f91azyfgai47	Mobile → Tổ 23 — 102, Tổ 23 — 102
4333	a5ae5ecd	AGV02	go_to	201	completed	2026-07-18 11:07:47.325721+07	2026-07-18 11:09:30.546468+07	2026-07-18 11:10:34.393484+07	event:continue	dpm8sunicfj8	Mobile → Tổ 22 — 101, Tổ 22 — 101
4334	3d4ecedd	AGV02	go_to	101	completed	2026-07-18 11:07:47.325721+07	2026-07-18 11:08:32.931683+07	2026-07-18 11:09:30.545547+07	hook_raised	dpm8sunicfj8	Mobile → Tổ 22 — 101, Tổ 22 — 101
4335	48872cfc	AGV02	go_to	81	completed	2026-07-18 11:07:47.326721+07	2026-07-18 11:10:34.394478+07	2026-07-18 11:13:31.133776+07	hook_raised	dpm8sunicfj8	Mobile → Tổ 22 — 101, Tổ 22 — 101
4336	7a4a8601	AGV02	go_charge	\N	completed	2026-07-18 11:07:47.327723+07	2026-07-18 11:13:31.134763+07	2026-07-18 11:13:53.069424+07	charge_arrived	dpm8sunicfj8	Mobile → Tổ 22 — 101, Tổ 22 — 101
4339	f4e90429	AGV02	go_to	102	completed	2026-07-18 11:14:20.724531+07	2026-07-18 11:15:36.506149+07	2026-07-18 11:16:15.795397+07	hook_raised	9c7oeumbjqo8	Mobile → Tổ 23 — 102, Tổ 23 — 102
4340	251d39c2	AGV02	go_to	81	completed	2026-07-18 11:14:20.726676+07	2026-07-18 11:17:02.262388+07	2026-07-18 11:19:29.925672+07	hook_raised	9c7oeumbjqo8	Mobile → Tổ 23 — 102, Tổ 23 — 102
4344	1eec0920	AGV02	go_to	101	completed	2026-07-18 11:20:15.130696+07	2026-07-18 11:21:09.928765+07	2026-07-18 11:21:47.383012+07	hook_raised	fkqoyyfdc289	Mobile → Tổ 22 — 101, Tổ 22 — 101
4345	a1e54547	AGV02	go_to	81	completed	2026-07-18 11:20:15.133711+07	2026-07-18 11:22:38.600391+07	2026-07-18 11:23:29.452881+07	hook_raised	fkqoyyfdc289	Mobile → Tổ 22 — 101, Tổ 22 — 101
4346	da79e42f	AGV02	go_charge	\N	completed	2026-07-18 11:20:15.13571+07	2026-07-18 11:23:29.45387+07	2026-07-18 11:23:48.26906+07	charge_arrived	fkqoyyfdc289	Mobile → Tổ 22 — 101, Tổ 22 — 101
4347	c02c3f68	AGV02	go_to	82	completed	2026-07-18 11:24:03.534993+07	2026-07-18 11:24:03.534993+07	2026-07-18 11:24:47.1291+07	event:continue	j8ktbdw90s58	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4349	51f844e9	AGV02	go_to	102	completed	2026-07-18 11:24:03.556997+07	2026-07-18 11:25:24.588458+07	2026-07-18 11:25:28.634429+07	hook_already_raised	j8ktbdw90s58	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4352	faa7e389	AGV02	go_to	81	completed	2026-07-18 11:24:03.563125+07	2026-07-18 11:26:16.007363+07	2026-07-18 11:39:34.089951+07	hook_raised	j8ktbdw90s58	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4353	5a076723	AGV02	go_charge	\N	completed	2026-07-18 11:24:03.567089+07	2026-07-18 11:39:34.090956+07	2026-07-18 11:39:35.670763+07	hook_already_raised	j8ktbdw90s58	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4337	a7261ae0	AGV02	go_to	82	completed	2026-07-18 11:14:20.693428+07	2026-07-18 11:14:20.693428+07	2026-07-18 11:15:36.505145+07	event:continue	9c7oeumbjqo8	Mobile → Tổ 23 — 102, Tổ 23 — 102
4361	ed3f39b1	AGV02	go_to	82	completed	2026-07-18 11:44:51.13085+07	2026-07-18 11:44:51.13085+07	2026-07-18 11:45:43.577914+07	event:continue	byj5yceex302	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4338	dc16c4e5	AGV02	go_to	202	completed	2026-07-18 11:14:20.725535+07	2026-07-18 11:16:15.795397+07	2026-07-18 11:17:02.261381+07	event:continue	9c7oeumbjqo8	Mobile → Tổ 23 — 102, Tổ 23 — 102
4341	57f60562	AGV02	go_charge	\N	completed	2026-07-18 11:14:20.728656+07	2026-07-18 11:19:29.925672+07	2026-07-18 11:19:52.58072+07	charge_arrived	9c7oeumbjqo8	Mobile → Tổ 23 — 102, Tổ 23 — 102
4342	2ac1670f	AGV02	go_to	82	completed	2026-07-18 11:20:15.119006+07	2026-07-18 11:20:15.119006+07	2026-07-18 11:21:09.926862+07	event:continue	fkqoyyfdc289	Mobile → Tổ 22 — 101, Tổ 22 — 101
4363	4cf643e6	AGV02	go_to	101	completed	2026-07-18 11:44:51.197847+07	2026-07-18 11:45:43.577914+07	2026-07-18 11:46:20.969265+07	hook_raised	byj5yceex302	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4343	80340bfd	AGV02	go_to	201	completed	2026-07-18 11:20:15.132711+07	2026-07-18 11:21:47.384113+07	2026-07-18 11:22:38.600391+07	event:continue	fkqoyyfdc289	Mobile → Tổ 22 — 101, Tổ 22 — 101
4348	f20fdfbb	AGV02	go_to	101	completed	2026-07-18 11:24:03.556107+07	2026-07-18 11:24:47.131069+07	2026-07-18 11:25:24.588458+07	hook_raised	j8ktbdw90s58	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4362	15f97286	AGV02	go_to	102	completed	2026-07-18 11:44:51.198848+07	2026-07-18 11:46:20.969265+07	2026-07-18 11:46:24.88718+07	hook_already_raised	byj5yceex302	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4350	5b0e5691	AGV02	go_to	202	completed	2026-07-18 11:24:03.559094+07	2026-07-18 11:25:28.635423+07	2026-07-18 11:26:08.439124+07	event:continue	j8ktbdw90s58	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4351	bb0e2d22	AGV02	go_to	201	completed	2026-07-18 11:24:03.562097+07	2026-07-18 11:26:08.441119+07	2026-07-18 11:26:16.006387+07	event:continue	j8ktbdw90s58	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4354	cfd1bcd0	AGV02	go_to	82	completed	2026-07-18 11:40:54.001598+07	2026-07-18 11:40:54.001598+07	2026-07-18 11:41:44.196029+07	event:continue	2q7zpl3ntzfi	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4364	13ccbafa	AGV02	go_to	81	completed	2026-07-18 11:44:51.203875+07	2026-07-18 11:47:14.952562+07	2026-07-18 11:48:03.311972+07	hook_raised	byj5yceex302	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4356	b967248b	AGV02	go_to	101	completed	2026-07-18 11:40:54.071633+07	2026-07-18 11:41:44.197023+07	2026-07-18 11:42:21.449832+07	hook_raised	2q7zpl3ntzfi	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4355	bb72fb0c	AGV02	go_to	102	completed	2026-07-18 11:40:54.072633+07	2026-07-18 11:42:21.449832+07	2026-07-18 11:42:25.455328+07	hook_already_raised	2q7zpl3ntzfi	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4359	1cf48b5d	AGV02	go_to	202	completed	2026-07-18 11:40:54.072633+07	2026-07-18 11:42:25.455328+07	2026-07-18 11:43:04.549383+07	event:continue	2q7zpl3ntzfi	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4357	75b02f9c	AGV02	go_to	201	completed	2026-07-18 11:40:54.074632+07	2026-07-18 11:43:04.550376+07	2026-07-18 11:43:10.923417+07	event:continue	2q7zpl3ntzfi	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4358	76784e17	AGV02	go_to	81	completed	2026-07-18 11:40:54.074632+07	2026-07-18 11:43:10.924417+07	2026-07-18 11:43:59.426833+07	hook_raised	2q7zpl3ntzfi	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4360	9de166e2	AGV02	go_charge	\N	completed	2026-07-18 11:40:54.075632+07	2026-07-18 11:43:59.427831+07	2026-07-18 11:44:19.239908+07	charge_arrived	2q7zpl3ntzfi	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4366	7f375306	AGV02	go_to	202	completed	2026-07-18 11:44:51.199849+07	2026-07-18 11:46:24.88718+07	2026-07-18 11:47:07.734717+07	event:continue	byj5yceex302	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4367	b2620a64	AGV02	go_to	201	completed	2026-07-18 11:44:51.202849+07	2026-07-18 11:47:07.734717+07	2026-07-18 11:47:14.952562+07	event:continue	byj5yceex302	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4365	148b282c	AGV02	go_charge	\N	completed	2026-07-18 11:44:51.204851+07	2026-07-18 11:48:03.31397+07	2026-07-18 11:48:22.305635+07	charge_arrived	byj5yceex302	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4368	e4cc9c15	AGV02	go_to	82	completed	2026-07-18 11:48:37.131118+07	2026-07-18 11:48:37.131118+07	2026-07-18 11:49:31.786561+07	event:continue	cwrqub92od9i	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4369	98c78f71	AGV02	go_to	101	completed	2026-07-18 11:48:37.142547+07	2026-07-18 11:49:31.787553+07	2026-07-18 11:50:11.063458+07	hook_raised	cwrqub92od9i	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4370	d8ef45c5	AGV02	go_to	102	completed	2026-07-18 11:48:37.143548+07	2026-07-18 11:50:11.063458+07	2026-07-18 11:50:15.382963+07	hook_already_raised	cwrqub92od9i	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4371	5308ece2	AGV02	go_to	202	completed	2026-07-18 11:48:37.143548+07	2026-07-18 11:50:15.382963+07	2026-07-18 11:51:00.009526+07	event:continue	cwrqub92od9i	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4372	3ab42678	AGV02	go_to	201	completed	2026-07-18 11:48:37.144547+07	2026-07-18 11:51:00.009526+07	2026-07-18 11:51:06.312392+07	event:continue	cwrqub92od9i	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4373	7ef74431	AGV02	go_to	81	completed	2026-07-18 11:48:37.144547+07	2026-07-18 11:51:06.312392+07	2026-07-18 11:51:58.226712+07	hook_raised	cwrqub92od9i	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
4374	c0c435ea	AGV02	go_charge	\N	completed	2026-07-18 11:48:37.145548+07	2026-07-18 11:51:58.226712+07	2026-07-18 11:52:16.88735+07	charge_arrived	cwrqub92od9i	Mobile → Tổ 22 — 101, Tổ 23 — 102, Tổ 22 — 101, Tổ 23 — 102
\.


--
-- Data for Name: agv_tasks; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agv_tasks (id, task_id, agv_id, destination, map_id, status, order_id, notes, created_at, updated_at, operator_name, operator_id, order_info) FROM stdin;
1	e2a674b8-2b3e-43bf-a7e6-4967660946fd	AGV01	17	1779790224391	failed	\N		2026-06-19 11:19:10.671533+07	2026-06-19 11:19:10.707704+07	\N	\N	\N
2	3af554fe-d6c4-4ab4-8bba-acb899b773cb	AGV01	16	1779790224391	failed	\N		2026-06-19 11:19:10.809504+07	2026-06-19 11:19:10.812246+07	\N	\N	\N
3	5a7e9e11-42ef-4239-92a3-b8acd8436095	AGV01	15	1779790224391	failed	\N		2026-06-19 11:19:10.851304+07	2026-06-19 11:19:10.853955+07	\N	\N	\N
4	366a5cf7-90d6-49fe-babd-174a2e5e31c1	AGV01	18	1779790224391	failed	\N		2026-06-19 11:26:20.836784+07	2026-06-19 11:26:20.842925+07	\N	\N	\N
5	1adfde9a-30be-4f76-b509-b33d0ac0f6be	AGV01	96	1779790224391	failed	\N		2026-06-19 11:26:20.883377+07	2026-06-19 11:26:20.887016+07	\N	\N	\N
6	41ed2982-fc0a-4ac4-9ae0-b316022f54ac	AGV01	69	1779790224391	failed	\N		2026-06-19 11:26:20.903435+07	2026-06-19 11:26:20.905131+07	\N	\N	\N
29	29a04d9c-ccca-4d63-8b99-8bf301d2c4e8	AGV01	16	1779790224391	failed	\N		2026-06-22 11:36:00.902628+07	2026-06-22 11:36:00.967658+07	Ma Đức Mạnh	TNG084090	\N
30	b25ef9e7-5532-4068-9783-547091d9a73f	AGV01	18	1779790224391	cancelled	0a13bdaa-9248-4fa3-a516-8071503a8f01		2026-06-23 13:50:55.849795+07	2026-07-16 14:17:55.654937+07	Ma Đức Mạnh	TNG084090	\N
7	b89921eb-a5df-445b-a0c6-b630212dbbd5	AGV01	18	1779790224391	cancelled	589f32a8-42f2-4965-9f8b-5a77f635d80e		2026-06-19 11:30:58.727156+07	2026-06-19 11:59:43.712374+07	\N	\N	\N
8	160625f7-dd34-44aa-869c-63a2180ca017	AGV01	96	1779790224391	cancelled	c0809ad0-599f-4f88-9000-77988ea331c4		2026-06-19 11:30:58.78106+07	2026-06-19 11:59:43.712374+07	\N	\N	\N
9	5131c4a0-e28d-4bdc-ab71-ffb6cc4bfcd4	AGV01	69	1779790224391	cancelled	045485d8-d625-4741-aac9-1bb403bd5885		2026-06-19 11:30:58.823941+07	2026-06-19 11:59:43.712374+07	\N	\N	\N
10	f9ee843c-f088-4f2c-a3e6-6cc709e6fbed	AGV01	18	1779790224391	cancelled	1ffc8c0c-ff0d-4224-ba9e-71d5472e2971		2026-06-19 11:47:23.820541+07	2026-06-19 11:59:43.712374+07	\N	\N	\N
11	2f566e92-1f3a-4b75-93c6-3adf576d8c08	AGV01	18	1779790224391	cancelled	05fd60b5-a9e3-4b75-bcc2-b71efd4cd34b		2026-06-19 11:56:51.326469+07	2026-06-19 11:59:43.712374+07	\N	\N	\N
12	8e885b47-aac8-48f5-ba30-4853b55ebd1e	AGV01	17	1779790224391	cancelled	96695638-8cdb-47b2-9565-2edfae588a3e		2026-06-19 11:56:51.404195+07	2026-06-19 11:59:43.712374+07	\N	\N	\N
13	3e204441-c1e3-4244-937f-7ecef021068d	AGV01	18	1779790224391	cancelled	2a83bb5e-ad85-4b76-a29c-427b76bc6132		2026-06-19 11:59:39.131668+07	2026-06-19 11:59:43.712374+07	\N	\N	\N
14	279e97c7-aaa0-4d10-b4b1-774c733993ca	AGV01	96	1779790224391	cancelled	6e54df4d-d109-46a9-9b18-10c536583267		2026-06-19 12:03:45.026937+07	2026-06-19 12:03:58.41502+07	\N	\N	\N
25	2c67a455-87a7-427b-a1d5-9a9770c8c87c	AGV01	18	1779790224391	cancelled	284b679e-6397-4423-b83c-5eaff88c00c3		2026-06-21 10:04:22.02799+07	2026-07-16 14:17:55.654937+07	Ma Đức Mạnh	TNG084090	\N
15	d4441068-6e97-4abc-8068-a58693c93b00	AGV01	96	1779790224391	cancelled	a44abe8b-3581-4f81-96a9-a6d5a6b4bc54		2026-06-19 15:46:33.526652+07	2026-06-19 15:48:57.851588+07	Ma Đức Mạnh	TNG084090	\N
16	53f46e22-ce4d-4d0b-ab74-a1d4973c403e	AGV01	69	1779790224391	cancelled	97fa6b2e-27c6-4aee-be20-9047252940c2		2026-06-19 15:46:33.637018+07	2026-06-19 15:48:57.851588+07	Ma Đức Mạnh	TNG084090	\N
26	b268947f-e661-4f93-ac07-bebd1a4ae951	AGV01	18	1779790224391	cancelled	bae35c14-4127-4ca2-8f47-0748d451b562		2026-06-22 11:18:10.492339+07	2026-07-16 14:17:55.654937+07	Ma Đức Mạnh	TNG084090	\N
17	1c464ee3-9632-45a1-810b-68867f6cb881	AGV01	18	1779790224391	cancelled	d63e6b0f-6745-4fae-bda4-b7c6479d1fd4		2026-06-19 15:51:21.462314+07	2026-06-19 15:55:27.362072+07	Ma Đức Mạnh	TNG084090	\N
19	6d74ada0-6d4a-41c3-b7e5-ba41ad28d351	AGV01	18	1779790224391	cancelled	46ae0bd4-deea-4c94-86b2-6b7045c85a5b		2026-06-19 16:09:34.943418+07	2026-06-19 16:09:52.571395+07	Ma Đức Mạnh	TNG084090	\N
18	ed606b88-4e9a-429d-a367-76ee0f529e04	AGV01	18	1779790224391	cancelled	a3e606d7-d569-455f-8e0e-637d3fef024b		2026-06-19 16:07:15.79363+07	2026-06-19 16:07:29.218989+07	Ma Đức Mạnh	TNG084090	\N
20	4e74a574-abbf-4d02-8df8-de374110a62b	AGV01	96	1779790224391	cancelled	ae741544-6f8b-4d6a-b127-f438d85a25f2		2026-06-19 16:09:35.06542+07	2026-06-19 16:09:52.571395+07	Ma Đức Mạnh	TNG084090	\N
21	87de1319-f652-4a39-bdf0-9462e57dcb1e	AGV01	69	1779790224391	cancelled	97d8b59f-7d2e-44dd-a239-4aadf8af840e		2026-06-19 16:09:35.106984+07	2026-06-19 16:09:52.571395+07	Ma Đức Mạnh	TNG084090	\N
22	555102ec-130a-4c00-a5c3-bbbfbf7ebb71	AGV01	17	1779790224391	cancelled	c7f2026c-8667-4399-9bb1-c2e203e56568		2026-06-19 16:09:35.126825+07	2026-06-19 16:09:52.571395+07	Ma Đức Mạnh	TNG084090	\N
23	6c1ff1ed-6051-4d06-acbf-11ae95521751	AGV01	16	1779790224391	cancelled	24c4ed7d-156d-480d-8a7e-c1489fdd3da2		2026-06-19 16:09:35.14798+07	2026-06-19 16:09:52.571395+07	Ma Đức Mạnh	TNG084090	\N
24	4d7cf5a2-b53e-4498-8452-ca3cbf8b861d	AGV01	15	1779790224391	cancelled	da939843-b897-469c-9a8d-81ff69f13832		2026-06-19 16:09:35.168563+07	2026-06-19 16:09:52.571395+07	Ma Đức Mạnh	TNG084090	\N
27	6ff6b902-4f80-4e43-b37e-c2af007acc06	AGV01	16	1779790224391	cancelled	9be60566-96db-400e-aad0-2c4eeaf4c5bb		2026-06-22 11:18:10.657384+07	2026-07-16 14:17:55.654937+07	Ma Đức Mạnh	TNG084090	\N
28	37dfbaef-7264-4d0b-aed4-b6be1eda6f47	AGV01	18	1779790224391	cancelled	321b9a3b-2988-4082-b5de-b26323759d3a		2026-06-22 11:36:00.692666+07	2026-07-16 14:17:55.654937+07	Ma Đức Mạnh	TNG084090	\N
\.


--
-- Data for Name: agv_workflow_templates; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agv_workflow_templates (id, template_id, name, steps, created_at, updated_at) FROM stdin;
1	8f292c63-e554-419e-b50b-ee8a9b0fbcb7	A01	[{"type": "move", "notes": "", "order": 1, "speed": 0.5, "waitSec": 30, "priority": "normal"}, {"type": "move", "notes": "", "order": 2, "speed": 0.5, "waitSec": 30, "priority": "normal"}]	2026-05-20 21:35:02.511991+07	2026-05-20 21:35:02.511991+07
3	7009cd36-a820-4522-b1ff-9504a59df4cf	A02	[{"type": "move", "notes": "", "order": 1, "speed": 0.5, "waitSec": 30, "priority": "normal"}, {"type": "move", "notes": "", "order": 2, "speed": 0.5, "waitSec": 30, "priority": "normal"}, {"type": "charge", "notes": "", "order": 3, "speed": 0.5, "waitSec": 30, "priority": "normal"}]	2026-05-21 15:10:20.851236+07	2026-05-21 15:10:20.851236+07
4	46885272-948a-4830-a974-79381a26f65a	A03	[{"type": "move", "notes": "", "order": 1, "speed": 0.5, "waitSec": 30, "priority": "normal"}]	2026-05-22 13:46:32.705539+07	2026-05-22 13:46:32.705539+07
5	f693a75b-191f-4c1c-91bf-6728e785c092	A04	[{"type": "move", "notes": "", "order": 1, "speed": 0.5, "waitSec": 30, "priority": "normal"}, {"type": "charge", "notes": "", "order": 2, "speed": 0.5, "waitSec": 30, "priority": "normal"}]	2026-05-26 13:10:41.699229+07	2026-05-26 13:10:41.699229+07
6	0fcd996d-faa9-445f-a091-035fc6b82050	Sạc Pin	[{"type": "charge", "notes": "", "order": 1, "speed": 0.5, "waitSec": 30, "priority": "normal"}]	2026-05-27 08:14:48.434685+07	2026-05-27 08:14:48.434685+07
7	96034fd2-8971-47fe-8bc9-dbbf0aeaa0bb	A05	[{"type": "move", "notes": "", "order": 1, "speed": 0.5, "waitSec": 30, "priority": "normal"}, {"type": "move", "notes": "", "order": 2, "speed": 0.5, "waitSec": 30, "priority": "normal"}, {"type": "move", "notes": "", "order": 3, "speed": 0.5, "waitSec": 30, "priority": "normal"}, {"type": "move", "notes": "", "order": 4, "speed": 0.5, "waitSec": 30, "priority": "normal"}, {"type": "charge", "notes": "", "order": 5, "speed": 0.5, "waitSec": 30, "priority": "normal"}]	2026-05-27 14:09:26.254941+07	2026-05-27 14:09:26.254941+07
8	312653cc-e6f2-4a8b-b4cf-1c9810ba2982	A06	[{"type": "move", "notes": "", "order": 1, "speed": 0.5, "waitSec": 30, "priority": "normal"}, {"type": "charge", "notes": "", "order": 2, "speed": 0.5, "waitSec": 30, "priority": "normal"}]	2026-05-29 14:29:16.356976+07	2026-05-29 14:29:16.356976+07
\.


--
-- Data for Name: agvs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.agvs (id, agv_id, serial_number, manufacturer, model, ip_address, current_map, created_at, updated_at, is_online) FROM stdin;
\.


--
-- Name: agv_integration_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.agv_integration_logs_id_seq', 1, true);


--
-- Name: agv_integrations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.agv_integrations_id_seq', 1, true);


--
-- Name: agv_map_benziers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.agv_map_benziers_id_seq', 146, true);


--
-- Name: agv_map_codes_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.agv_map_codes_id_seq', 494, true);


--
-- Name: agv_map_points_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.agv_map_points_id_seq', 3527, true);


--
-- Name: agv_map_roads_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.agv_map_roads_id_seq', 4781, true);


--
-- Name: agv_task_executions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.agv_task_executions_id_seq', 4374, true);


--
-- Name: agv_tasks_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.agv_tasks_id_seq', 30, true);


--
-- Name: agv_workflow_templates_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.agv_workflow_templates_id_seq', 8, true);


--
-- Name: agvs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.agvs_id_seq', 1, false);


--
-- Name: agv_devices agv_devices_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_devices
    ADD CONSTRAINT agv_devices_pkey PRIMARY KEY (name);


--
-- Name: agv_integration_logs agv_integration_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_integration_logs
    ADD CONSTRAINT agv_integration_logs_pkey PRIMARY KEY (id);


--
-- Name: agv_integrations agv_integrations_conn_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_integrations
    ADD CONSTRAINT agv_integrations_conn_id_key UNIQUE (conn_id);


--
-- Name: agv_integrations agv_integrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_integrations
    ADD CONSTRAINT agv_integrations_pkey PRIMARY KEY (id);


--
-- Name: agv_map_benziers agv_map_benziers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_map_benziers
    ADD CONSTRAINT agv_map_benziers_pkey PRIMARY KEY (id);


--
-- Name: agv_map_codes agv_map_codes_map_id_code_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_map_codes
    ADD CONSTRAINT agv_map_codes_map_id_code_id_key UNIQUE (map_id, code_id);


--
-- Name: agv_map_codes agv_map_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_map_codes
    ADD CONSTRAINT agv_map_codes_pkey PRIMARY KEY (id);


--
-- Name: agv_map_points agv_map_points_map_id_name_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_map_points
    ADD CONSTRAINT agv_map_points_map_id_name_id_key UNIQUE (map_id, name_id);


--
-- Name: agv_map_points agv_map_points_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_map_points
    ADD CONSTRAINT agv_map_points_pkey PRIMARY KEY (id);


--
-- Name: agv_map_roads agv_map_roads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_map_roads
    ADD CONSTRAINT agv_map_roads_pkey PRIMARY KEY (id);


--
-- Name: agv_maps agv_maps_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_maps
    ADD CONSTRAINT agv_maps_pkey PRIMARY KEY (id);


--
-- Name: agv_schedules agv_schedules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_schedules
    ADD CONSTRAINT agv_schedules_pkey PRIMARY KEY (id);


--
-- Name: agv_task_executions agv_task_executions_cmd_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_task_executions
    ADD CONSTRAINT agv_task_executions_cmd_id_key UNIQUE (cmd_id);


--
-- Name: agv_task_executions agv_task_executions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_task_executions
    ADD CONSTRAINT agv_task_executions_pkey PRIMARY KEY (id);


--
-- Name: agv_tasks agv_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_tasks
    ADD CONSTRAINT agv_tasks_pkey PRIMARY KEY (id);


--
-- Name: agv_tasks agv_tasks_task_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_tasks
    ADD CONSTRAINT agv_tasks_task_id_key UNIQUE (task_id);


--
-- Name: agv_workflow_templates agv_workflow_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_workflow_templates
    ADD CONSTRAINT agv_workflow_templates_pkey PRIMARY KEY (id);


--
-- Name: agv_workflow_templates agv_workflow_templates_template_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_workflow_templates
    ADD CONSTRAINT agv_workflow_templates_template_id_key UNIQUE (template_id);


--
-- Name: agvs agvs_agv_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agvs
    ADD CONSTRAINT agvs_agv_id_key UNIQUE (agv_id);


--
-- Name: agvs agvs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agvs
    ADD CONSTRAINT agvs_pkey PRIMARY KEY (id);


--
-- Name: idx_agv_devices_last_seen; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agv_devices_last_seen ON public.agv_devices USING btree (last_seen);


--
-- Name: idx_codes_map; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_codes_map ON public.agv_map_codes USING btree (map_id);


--
-- Name: idx_int_logs_conn_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_int_logs_conn_time ON public.agv_integration_logs USING btree (conn_id, created_at DESC);


--
-- Name: idx_map_points_team; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_map_points_team ON public.agv_map_points USING btree (((action ->> 'team'::text))) WHERE ((action ->> 'locationType'::text) = 'DROPOFF'::text);


--
-- Name: idx_points_map; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_points_map ON public.agv_map_points USING btree (map_id);


--
-- Name: idx_roads_map; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_roads_map ON public.agv_map_roads USING btree (map_id);


--
-- Name: agv_devices trg_agv_devices_updated; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_agv_devices_updated BEFORE UPDATE ON public.agv_devices FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: agv_map_benziers agv_map_benziers_map_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_map_benziers
    ADD CONSTRAINT agv_map_benziers_map_id_fkey FOREIGN KEY (map_id) REFERENCES public.agv_maps(id) ON DELETE CASCADE;


--
-- Name: agv_map_codes agv_map_codes_map_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_map_codes
    ADD CONSTRAINT agv_map_codes_map_id_fkey FOREIGN KEY (map_id) REFERENCES public.agv_maps(id) ON DELETE CASCADE;


--
-- Name: agv_map_points agv_map_points_map_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_map_points
    ADD CONSTRAINT agv_map_points_map_id_fkey FOREIGN KEY (map_id) REFERENCES public.agv_maps(id) ON DELETE CASCADE;


--
-- Name: agv_map_roads agv_map_roads_map_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agv_map_roads
    ADD CONSTRAINT agv_map_roads_map_id_fkey FOREIGN KEY (map_id) REFERENCES public.agv_maps(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict SgBgajTPDTcYYG3dTLcbqFbW7Si6aeGgJhh6TZzmbm7hLwPpiPnUjORDgbkufUi

