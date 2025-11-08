DROP TABLE IF EXISTS gestures;
DROP TABLE IF EXISTS checklist_items;
DROP TABLE IF EXISTS workouts;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(80) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    reg_number VARCHAR(20) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password VARCHAR(200) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE workouts (
    id SERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    description TEXT,
    equipment TEXT,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    geotag_id INTEGER REFERENCES geotags(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE checklist_items (
    id SERIAL PRIMARY KEY,
    task VARCHAR(255) NOT NULL,
    done BOOLEAN DEFAULT FALSE,
    workout_id INTEGER REFERENCES workouts(id) ON DELETE CASCADE
);

CREATE TABLE gestures (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    action VARCHAR(200),
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
);

-- Table for saved public workouts
CREATE TABLE saved_workouts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    public_workout_id INTEGER REFERENCES public_workouts(id),
    name VARCHAR(120) NOT NULL,
    description TEXT,
    equipment TEXT,
    type VARCHAR(50),
    muscles TEXT[],
    level VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, public_workout_id)
);

-- Public API table
CREATE TABLE public_workouts (
    id SERIAL PRIMARY KEY,
    type VARCHAR(50),
    name VARCHAR(100),
    muscles TEXT[],
    equipment TEXT,
    instructions TEXT,
    level VARCHAR(20)
);

