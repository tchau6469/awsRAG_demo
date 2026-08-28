CREATE TABLE IF NOT EXISTS public.parks (
    park_code VARCHAR(4) PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    state_code CHAR(2) NOT NULL CHECK (state_code ~ '^[A-Z]{2}$'),
    established_year SMALLINT NOT NULL CHECK (established_year BETWEEN 1872 AND 2100)
);

CREATE INDEX IF NOT EXISTS parks_state_code_idx
    ON public.parks (state_code);

CREATE INDEX IF NOT EXISTS parks_established_year_idx
    ON public.parks (established_year);
