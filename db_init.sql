DROP TABLE IF EXISTS saved_workouts CASCADE;
DROP TABLE IF EXISTS gestures CASCADE;
DROP TABLE IF EXISTS checklist_items CASCADE;
DROP TABLE IF EXISTS workouts CASCADE;
DROP TABLE IF EXISTS public_workouts CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- USERS TABLE
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    reg_number VARCHAR(20) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password VARCHAR(200) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- PUBLIC WORKOUTS
CREATE TABLE IF NOT EXISTS public_workouts (
    id SERIAL PRIMARY KEY,
    type VARCHAR(50),
    name VARCHAR(100),
    muscles TEXT[],
    equipment TEXT,
    description TEXT,
    instructions TEXT,
    level VARCHAR(20)
);

-- USER-CREATED WORKOUTS
CREATE TABLE IF NOT EXISTS workouts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    description TEXT,
    equipment TEXT,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    image_url TEXT
);

-- SAVED PUBLIC WORKOUTS
CREATE TABLE IF NOT EXISTS saved_workouts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    public_workout_id INTEGER REFERENCES public_workouts(id),
    name VARCHAR(120) NOT NULL,
    description TEXT,
    instructions TEXT,
    equipment TEXT,
    type VARCHAR(50),
    muscles TEXT[],
    level VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, public_workout_id)
);

-- CHECKLIST ITEMS
CREATE TABLE IF NOT EXISTS checklist_items (
    id SERIAL PRIMARY KEY,
    task TEXT NOT NULL,
    done BOOLEAN DEFAULT FALSE,
    workout_id INTEGER NOT NULL REFERENCES workouts(id) ON DELETE CASCADE
);

-- GESTURES
CREATE TABLE IF NOT EXISTS gestures (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    action VARCHAR(200),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
);
