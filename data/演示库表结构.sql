CREATE TABLE course_attempts(attempt_id INTEGER PRIMARY KEY,user_id TEXT NOT NULL REFERENCES students,course_id TEXT NOT NULL REFERENCES courses,term TEXT NOT NULL REFERENCES semesters,attempt_no INTEGER NOT NULL,exam_type TEXT NOT NULL CHECK(exam_type IN('regular','makeup','retake')),status TEXT NOT NULL CHECK(status IN('passed','failed','enrolled')),score REAL CHECK(score BETWEEN 0 AND 100),grade_label TEXT,grade_point REAL,valid INTEGER NOT NULL DEFAULT 1,UNIQUE(user_id,course_id,attempt_no),CHECK((status='enrolled' AND score IS NULL AND grade_point IS NULL) OR (status IN('passed','failed') AND score IS NOT NULL)));

CREATE TABLE courses(course_id TEXT PRIMARY KEY,plan_id TEXT NOT NULL REFERENCES training_plans,code TEXT NOT NULL,original_code TEXT NOT NULL,name TEXT NOT NULL,credits REAL NOT NULL CHECK(credits>=0),hours REAL,category TEXT NOT NULL,nature TEXT NOT NULL,suggested_term INTEGER NOT NULL,grading_mode TEXT NOT NULL,gpa_included INTEGER NOT NULL CHECK(gpa_included IN(0,1)),gpa_exclusion_reason TEXT NOT NULL);

CREATE TABLE demo_snapshots(user_id TEXT PRIMARY KEY REFERENCES students,term TEXT REFERENCES semesters,snapshot_json TEXT NOT NULL,history_complete INTEGER NOT NULL,timetable_complete INTEGER NOT NULL);

CREATE TABLE enrollments(user_id TEXT REFERENCES students,offering_id TEXT REFERENCES offerings,status TEXT NOT NULL CHECK(status='enrolled'),PRIMARY KEY(user_id,offering_id));

CREATE TABLE erke_activities(activity_id TEXT PRIMARY KEY,user_id TEXT REFERENCES students,term TEXT REFERENCES semesters,name TEXT NOT NULL,dimension_id TEXT REFERENCES erke_dimensions,activity_date TEXT NOT NULL,role TEXT NOT NULL,hours REAL NOT NULL,recognition_key TEXT NOT NULL,approval_status TEXT NOT NULL CHECK(approval_status IN('approved','pending','rejected')),is_demo INTEGER NOT NULL CHECK(is_demo=1));

CREATE TABLE erke_dimensions(dimension_id TEXT PRIMARY KEY,name TEXT NOT NULL,full_score REAL NOT NULL,base_cap REAL NOT NULL,extension_cap REAL NOT NULL);

CREATE TABLE erke_records(record_id INTEGER PRIMARY KEY,activity_id TEXT REFERENCES erke_activities,rule_id TEXT REFERENCES erke_rules,detail_json TEXT NOT NULL);

CREATE TABLE erke_rules(rule_id TEXT PRIMARY KEY,dimension_id TEXT REFERENCES erke_dimensions,section TEXT NOT NULL,title TEXT NOT NULL,rule_json TEXT NOT NULL,version TEXT NOT NULL);

CREATE TABLE erke_summaries(user_id TEXT REFERENCES students,term TEXT REFERENCES semesters,dimension_id TEXT REFERENCES erke_dimensions,base_score REAL NOT NULL,extension_score REAL NOT NULL,total_score REAL NOT NULL,rule_scores_json TEXT NOT NULL,PRIMARY KEY(user_id,term,dimension_id));

CREATE TABLE gpa_summaries(user_id TEXT REFERENCES students,term TEXT NOT NULL,scope TEXT NOT NULL,weighted_points REAL NOT NULL,included_credits REAL NOT NULL,gpa REAL,PRIMARY KEY(user_id,term,scope));

CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);

CREATE TABLE offering_meetings(meeting_id TEXT PRIMARY KEY,offering_id TEXT REFERENCES offerings,weekday INTEGER CHECK(weekday BETWEEN 1 AND 7),start_period INTEGER CHECK(start_period BETWEEN 1 AND 12),end_period INTEGER CHECK(end_period BETWEEN 1 AND 12),weeks_json TEXT NOT NULL,week_pattern TEXT NOT NULL,room TEXT NOT NULL,campus TEXT NOT NULL,CHECK(end_period>=start_period));

CREATE TABLE offerings(offering_id TEXT PRIMARY KEY,course_id TEXT REFERENCES courses,term TEXT REFERENCES semesters,section_id TEXT NOT NULL,eligible_major TEXT NOT NULL,eligible_entry_year INTEGER NOT NULL,selection_restrictions TEXT NOT NULL);

CREATE TABLE personal_service_accounts(user_id TEXT PRIMARY KEY REFERENCES students,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN('active','disabled')));

CREATE TABLE plan_requirements(plan_id TEXT REFERENCES training_plans,category TEXT,minimum_credits REAL NOT NULL,PRIMARY KEY(plan_id,category));

CREATE TABLE preferences(user_id TEXT PRIMARY KEY REFERENCES students,goal TEXT NOT NULL,interests TEXT NOT NULL,max_term_credits REAL NOT NULL,preferred_free_day INTEGER);

CREATE TABLE prerequisites(course_id TEXT REFERENCES courses,prerequisite_id TEXT REFERENCES courses,PRIMARY KEY(course_id,prerequisite_id));

CREATE TABLE semesters(term TEXT PRIMARY KEY,academic_year TEXT NOT NULL,semester INTEGER NOT NULL,start_date TEXT NOT NULL,weeks INTEGER NOT NULL);

CREATE TABLE students(user_id TEXT PRIMARY KEY,name TEXT NOT NULL,college TEXT NOT NULL,major TEXT NOT NULL,entry_year INTEGER NOT NULL,year_level INTEGER NOT NULL,campus TEXT NOT NULL,plan_id TEXT NOT NULL REFERENCES training_plans,scenario TEXT NOT NULL,is_demo INTEGER NOT NULL CHECK(is_demo=1));

CREATE TABLE training_plans(plan_id TEXT PRIMARY KEY,major TEXT NOT NULL,college TEXT NOT NULL,version INTEGER NOT NULL,duration TEXT NOT NULL,graduation_credits REAL NOT NULL,source TEXT NOT NULL,limitations TEXT NOT NULL);

CREATE TABLE website_accounts(user_id TEXT PRIMARY KEY REFERENCES students,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN('active','disabled')));

CREATE VIEW current_course_status AS SELECT a.* FROM course_attempts a WHERE a.valid=1 AND NOT EXISTS(SELECT 1 FROM course_attempts b WHERE b.user_id=a.user_id AND b.course_id=a.course_id AND b.valid=1 AND b.attempt_no>a.attempt_no);

CREATE VIEW demo_profiles AS SELECT s.*,a.username,p.goal,p.interests,p.max_term_credits FROM students s JOIN website_accounts a USING(user_id) JOIN preferences p USING(user_id);

CREATE VIEW student_timetable AS SELECT e.user_id,o.term,o.section_id,c.code,c.name,c.credits,m.* FROM enrollments e JOIN offerings o USING(offering_id) JOIN courses c USING(course_id) JOIN offering_meetings m USING(offering_id);
