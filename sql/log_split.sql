CREATE TABLE log_split (
    id integer primary key generated always as identity,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    subject_id character varying(255) NOT NULL,
    date date NOT NULL,
    task_id character varying(255) NOT NULL,
    device_id character varying(255) NOT NULL,
    sensor_id character varying(255) NOT NULL,
    hdf5_file_path text NOT NULL
);


ALTER TABLE log_split OWNER TO neuroboother;
GRANT SELECT ON TABLE log_split TO neurovisualizer;

