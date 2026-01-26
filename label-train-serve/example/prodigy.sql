CREATE OR REPLACE FUNCTION labeled_of_dataset_edrs(dataset_name text)
    RETURNS SETOF text
    LANGUAGE sql
    AS $$
    -- vendor_message_id of labeled examples
    -- FIXME prodigy html breaks json
    SELECT
        replace(encode(content, 'escape'), '\\"', '\"')::json #>> '{meta,vendor_message_id}' AS vendor_message_id
        --     , encode(content, 'escape')::text
    FROM
        link
    LEFT JOIN dataset ON dataset.id = link.dataset_id
    LEFT JOIN example ON example.id = link.example_id
WHERE
    dataset.name = dataset_name;
$$;

-- select * from labeled_of_dataset_edrs('ads');
