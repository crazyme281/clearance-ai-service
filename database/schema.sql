-- ============================================================
-- SmartClearX — full schema as applied to the live Supabase project
-- ("Clearance system", ref jtmbzqisoeliydwljxrm). This file is a
-- reference/replay script — the database itself already has all of
-- this. Safe to re-run on a fresh project (everything is
-- `if not exists` / `or replace` / `drop ... if exists` first).
-- ============================================================

-- ---------- core org structure ----------
create table if not exists institutions (
    id            bigint generated always as identity primary key,
    name          text not null,
    short_name    text not null unique,
    status        text not null default 'active' check (status in ('active','suspended','pending')),
    created_at    timestamptz not null default now()
);

create table if not exists faculties (
    id             bigint generated always as identity primary key,
    institution_id bigint not null references institutions(id) on delete cascade,
    name           text not null,
    code           text
);

create table if not exists departments (
    id             bigint generated always as identity primary key,
    institution_id bigint not null references institutions(id) on delete cascade,
    faculty_id     bigint references faculties(id) on delete set null,
    name           text not null,
    code           text,
    sla_hours      int not null default 48
);

-- ---------- profiles + role tables ----------
create table if not exists profiles (
    id             uuid primary key references auth.users(id) on delete cascade,
    institution_id bigint references institutions(id) on delete set null,
    role           text not null default 'student' check (role in (
                       'super_admin','vc_academics','institution_admin',
                       'registry','dean','faculty_officer','hod',
                       'sub_admin','department_officer','bursary','student'
                   )),
    first_name     text not null,
    last_name      text not null,
    email          text not null unique,
    status         text not null default 'pending' check (status in ('active','pending','suspended','rejected')),
    phone          text,
    created_at     timestamptz not null default now()
);

create table if not exists student_profiles (
    id             bigint generated always as identity primary key,
    profile_id     uuid not null unique references profiles(id) on delete cascade,
    institution_id bigint references institutions(id) on delete set null,
    matric_number  text not null,
    department_id  bigint references departments(id) on delete set null,
    faculty_id     bigint references faculties(id) on delete set null,
    level          text,
    programme      text,
    created_at     timestamptz not null default now()
);

create table if not exists staff_profiles (
    id             bigint generated always as identity primary key,
    profile_id     uuid not null unique references profiles(id) on delete cascade,
    department_id  bigint references departments(id) on delete set null,
    faculty_id     bigint references faculties(id) on delete set null,
    designation    text,
    office_contact text
);

-- ---------- clearance workflow ----------
create table if not exists clearance_requests (
    id             bigint generated always as identity primary key,
    student_id     bigint not null references student_profiles(id) on delete cascade,
    institution_id bigint references institutions(id) on delete set null,
    status         text not null default 'draft' check (status in (
                       'draft','submitted','in_progress','pending_payment',
                       'approved','rejected','escalated','completed'
                   )),
    academic_year  text,
    semester       text,
    submitted_at   timestamptz,
    completed_at   timestamptz,
    created_at     timestamptz not null default now()
);

create table if not exists clearance_stage_instances (
    id                    bigint generated always as identity primary key,
    clearance_request_id  bigint not null references clearance_requests(id) on delete cascade,
    stage_order           smallint not null,
    stage_name            text not null,
    approver_role         text not null,
    assigned_to           uuid references profiles(id) on delete set null,
    status                text not null default 'pending' check (status in (
                              'pending','in_review','approved','rejected','escalated','skipped'
                          )),
    sla_deadline          timestamptz,
    reviewer_id           uuid references profiles(id) on delete set null,
    reviewed_at           timestamptz,
    rejection_reason      text,
    comments              text,
    unique (clearance_request_id, stage_order)
);

create table if not exists clearance_requirements (
    id             bigint generated always as identity primary key,
    institution_id bigint not null references institutions(id) on delete cascade,
    department_id  bigint references departments(id) on delete cascade,
    requirement_type text not null check (requirement_type in ('document','payment')),
    name           text not null,
    description    text,
    is_mandatory   boolean not null default true
);

create table if not exists student_documents (
    id             bigint generated always as identity primary key,
    student_id     bigint not null references student_profiles(id) on delete cascade,
    request_id     bigint references clearance_requests(id) on delete cascade,
    requirement_id bigint references clearance_requirements(id) on delete set null,
    doc_type       text not null,
    file_path      text not null,
    status         text not null default 'pending' check (status in (
                       'pending','verified','rejected','requires_correction'
                   )),
    ai_pre_approved boolean,
    created_at     timestamptz not null default now()
);

create table if not exists payment_records (
    id             bigint generated always as identity primary key,
    student_id     bigint not null references student_profiles(id) on delete cascade,
    requirement_id bigint references clearance_requirements(id) on delete set null,
    amount         numeric(12,2) not null default 0,
    currency       text not null default 'NGN',
    reference      text,
    status         text not null default 'pending' check (status in (
                       'pending','verified','rejected','flagged'
                   )),
    created_at     timestamptz not null default now()
);

create table if not exists ai_chat_logs (
    id             bigint generated always as identity primary key,
    profile_id     uuid not null references profiles(id) on delete cascade,
    role           text not null check (role in ('user','assistant')),
    content        text not null,
    tool_calls     jsonb,
    created_at     timestamptz not null default now()
);

-- ---------- indexes (every FK is covered) ----------
create index if not exists idx_ai_chat_logs_profile_id on ai_chat_logs(profile_id);
create index if not exists idx_clearance_requests_institution_id on clearance_requests(institution_id);
create index if not exists idx_clearance_requests_student_id on clearance_requests(student_id);
create index if not exists idx_clearance_requirements_department_id on clearance_requirements(department_id);
create index if not exists idx_clearance_requirements_institution_id on clearance_requirements(institution_id);
create index if not exists idx_clearance_stage_instances_assigned_to on clearance_stage_instances(assigned_to);
create index if not exists idx_clearance_stage_instances_reviewer_id on clearance_stage_instances(reviewer_id);
create index if not exists idx_clearance_stage_instances_request_id on clearance_stage_instances(clearance_request_id);
create index if not exists idx_departments_faculty_id on departments(faculty_id);
create index if not exists idx_departments_institution_id on departments(institution_id);
create index if not exists idx_faculties_institution_id on faculties(institution_id);
create index if not exists idx_payment_records_requirement_id on payment_records(requirement_id);
create index if not exists idx_payment_records_student_id on payment_records(student_id);
create index if not exists idx_profiles_institution_id on profiles(institution_id);
create index if not exists idx_staff_profiles_department_id on staff_profiles(department_id);
create index if not exists idx_staff_profiles_faculty_id on staff_profiles(faculty_id);
create index if not exists idx_student_documents_request_id on student_documents(request_id);
create index if not exists idx_student_documents_requirement_id on student_documents(requirement_id);
create index if not exists idx_student_documents_student_id on student_documents(student_id);
create index if not exists idx_student_profiles_department_id on student_profiles(department_id);
create index if not exists idx_student_profiles_faculty_id on student_profiles(faculty_id);
create index if not exists idx_student_profiles_institution_id on student_profiles(institution_id);

-- ---------- officer-review helper functions ----------
-- Boolean-only SECURITY DEFINER helpers so RLS policies on four different
-- tables can share one join. `anon` cannot call these at all; `authenticated`
-- can (required for RLS evaluation), but they only ever answer "can I
-- review X" — never return row data.
create or replace function public.is_reviewer_for_stage(stage_id bigint)
returns boolean language sql security definer stable set search_path = public as $$
  select exists (
    select 1
    from clearance_stage_instances csi
    join clearance_requests cr on cr.id = csi.clearance_request_id
    join student_profiles sp on sp.id = cr.student_id
    join staff_profiles st on st.profile_id = auth.uid()
    join profiles p on p.id = st.profile_id
    where csi.id = stage_id
      and p.role = csi.approver_role
      and p.status = 'active'  -- pending/suspended staff cannot review
      and (st.department_id is null or st.department_id = sp.department_id)
  );
$$;

create or replace function public.is_reviewer_for_request(req_id bigint)
returns boolean language sql security definer stable set search_path = public as $$
  select exists (
    select 1 from clearance_stage_instances csi
    where csi.clearance_request_id = req_id and public.is_reviewer_for_stage(csi.id)
  );
$$;

create or replace function public.is_reviewer_for_student(sid bigint)
returns boolean language sql security definer stable set search_path = public as $$
  select exists (
    select 1 from clearance_requests cr
    where cr.student_id = sid and public.is_reviewer_for_request(cr.id)
  );
$$;

-- Institution admin helper: is the caller the active institution_admin
-- for the given institution? Backs all admin-provisioning policies below.
create or replace function public.is_institution_admin_for(inst_id bigint)
returns boolean language sql security definer stable set search_path = public as $$
  select exists (
    select 1 from profiles p
    where p.id = auth.uid()
      and p.role = 'institution_admin'
      and p.status = 'active'
      and p.institution_id = inst_id
  );
$$;

revoke all on function public.is_reviewer_for_stage(bigint) from anon, authenticated, public;
revoke all on function public.is_reviewer_for_request(bigint) from anon, authenticated, public;
revoke all on function public.is_reviewer_for_student(bigint) from anon, authenticated, public;
revoke all on function public.is_institution_admin_for(bigint) from anon, authenticated, public;
grant execute on function public.is_reviewer_for_stage(bigint) to authenticated;
grant execute on function public.is_reviewer_for_request(bigint) to authenticated;
grant execute on function public.is_reviewer_for_student(bigint) to authenticated;
grant execute on function public.is_institution_admin_for(bigint) to authenticated;

-- ---------- workflow auto-advance ----------
-- When a stage's status changes, roll the parent clearance_requests.status
-- up: any rejection -> 'rejected', all stages approved -> 'completed', else
-- 'in_progress'. SECURITY DEFINER because the officer who triggers this
-- has no direct UPDATE grant on clearance_requests.
create or replace function public.sync_clearance_request_status()
returns trigger language plpgsql security definer set search_path = public as $$
declare
  total int;
  approved int;
  any_rejected boolean;
begin
  select count(*), count(*) filter (where status = 'approved'), bool_or(status = 'rejected')
    into total, approved, any_rejected
    from clearance_stage_instances
    where clearance_request_id = new.clearance_request_id;

  if any_rejected then
    update clearance_requests set status = 'rejected' where id = new.clearance_request_id;
  elsif approved = total and total > 0 then
    update clearance_requests set status = 'completed', completed_at = now() where id = new.clearance_request_id;
  elsif approved > 0 then
    update clearance_requests set status = 'in_progress' where id = new.clearance_request_id;
  end if;
  return new;
end;
$$;

drop trigger if exists trg_sync_clearance_request_status on clearance_stage_instances;
create trigger trg_sync_clearance_request_status
    after update of status on clearance_stage_instances
    for each row execute function public.sync_clearance_request_status();

-- ---------- document storage ----------
insert into storage.buckets (id, name, public)
values ('clearance-documents', 'clearance-documents', false)
on conflict (id) do nothing;

drop policy if exists "clearance-documents: students manage own folder" on storage.objects;
create policy "clearance-documents: students manage own folder" on storage.objects
    for all using (
        bucket_id = 'clearance-documents' and (storage.foldername(name))[1] = (select auth.uid())::text
    )
    with check (
        bucket_id = 'clearance-documents' and (storage.foldername(name))[1] = (select auth.uid())::text
    );

-- ---------- row level security ----------
alter table institutions enable row level security;
alter table faculties enable row level security;
alter table departments enable row level security;
alter table profiles enable row level security;
alter table student_profiles enable row level security;
alter table staff_profiles enable row level security;
alter table clearance_requests enable row level security;
alter table clearance_stage_instances enable row level security;
alter table clearance_requirements enable row level security;
alter table student_documents enable row level security;
alter table payment_records enable row level security;
alter table ai_chat_logs enable row level security;

-- institutions: anyone can read; any authenticated user can create one
-- (bootstrapping a new institution IS the institution_admin signup flow —
-- there's no admin to gate it before the first one exists). Faculties/
-- departments/requirements, once an institution exists, are locked to
-- that institution's own admin.
drop policy if exists "institutions: public read" on institutions;
create policy "institutions: public read" on institutions for select using (true);
drop policy if exists "institutions: authenticated users can create" on institutions;
create policy "institutions: authenticated users can create" on institutions
    for insert with check ((select auth.role()) = 'authenticated');

drop policy if exists "faculties: public read" on faculties;
create policy "faculties: public read" on faculties for select using (true);
drop policy if exists "faculties: admin creates within own institution" on faculties;
create policy "faculties: admin creates within own institution" on faculties
    for insert with check (public.is_institution_admin_for(institution_id));

drop policy if exists "departments: public read" on departments;
create policy "departments: public read" on departments for select using (true);
drop policy if exists "departments: admin creates within own institution" on departments;
create policy "departments: admin creates within own institution" on departments
    for insert with check (public.is_institution_admin_for(institution_id));

drop policy if exists "profiles: read own or reviewable student" on profiles;
drop policy if exists "profiles: admin reads own institution" on profiles;
drop policy if exists "profiles: read own, reviewable student, or own institution as admin" on profiles;
create policy "profiles: read own, reviewable student, or own institution as admin" on profiles
    for select using (
        (select auth.uid()) = id
        or exists (
            select 1 from student_profiles sp
            where sp.profile_id = profiles.id and public.is_reviewer_for_student(sp.id)
        )
        or public.is_institution_admin_for(institution_id)
    );
drop policy if exists "profiles: update own row" on profiles;
drop policy if exists "profiles: admin updates own institution" on profiles;
drop policy if exists "profiles: update own row or own institution as admin" on profiles;
create policy "profiles: update own row or own institution as admin" on profiles
    for update using (
        (select auth.uid()) = id
        or public.is_institution_admin_for(institution_id)
    );
drop policy if exists "profiles: insert own row" on profiles;
create policy "profiles: insert own row" on profiles for insert with check ((select auth.uid()) = id);

drop policy if exists "student_profiles: read own or reviewable" on student_profiles;
drop policy if exists "student_profiles: read own, reviewable, or own institution as admin" on student_profiles;
create policy "student_profiles: read own, reviewable, or own institution as admin" on student_profiles
    for select using (
        (select auth.uid()) = profile_id
        or public.is_reviewer_for_student(id)
        or public.is_institution_admin_for(institution_id)
    );
drop policy if exists "student_profiles: insert own row" on student_profiles;
create policy "student_profiles: insert own row" on student_profiles for insert with check ((select auth.uid()) = profile_id);

drop policy if exists "staff_profiles: read own or staff directory" on staff_profiles;
drop policy if exists "staff_profiles: admin reads own institution" on staff_profiles;
drop policy if exists "staff_profiles: read own, directory, or own institution as admin" on staff_profiles;
create policy "staff_profiles: read own, directory, or own institution as admin" on staff_profiles
    for select using (
        (select auth.uid()) = profile_id
        or exists (select 1 from profiles p where p.id = (select auth.uid()) and p.role <> 'student')
        or exists (
            select 1 from profiles p
            where p.id = staff_profiles.profile_id and public.is_institution_admin_for(p.institution_id)
        )
    );
drop policy if exists "staff_profiles: insert own row" on staff_profiles;
create policy "staff_profiles: insert own row" on staff_profiles for insert with check ((select auth.uid()) = profile_id);

drop policy if exists "clearance_requests: read own or reviewable" on clearance_requests;
drop policy if exists "clearance_requests: read own, reviewable, or own institution as admin" on clearance_requests;
create policy "clearance_requests: read own, reviewable, or own institution as admin" on clearance_requests
    for select using (
        exists (select 1 from student_profiles sp where sp.id = student_id and sp.profile_id = (select auth.uid()))
        or public.is_reviewer_for_request(id)
        or public.is_institution_admin_for(institution_id)
    );
drop policy if exists "clearance_requests: student inserts own" on clearance_requests;
create policy "clearance_requests: student inserts own" on clearance_requests
    for insert with check (
        exists (select 1 from student_profiles sp where sp.id = student_id and sp.profile_id = (select auth.uid()))
    );

drop policy if exists "clearance_stage_instances: read own or reviewable" on clearance_stage_instances;
create policy "clearance_stage_instances: read own or reviewable" on clearance_stage_instances
    for select using (
        exists (
            select 1 from clearance_requests cr
            join student_profiles sp on sp.id = cr.student_id
            where cr.id = clearance_request_id and sp.profile_id = (select auth.uid())
        )
        or public.is_reviewer_for_stage(id)
    );
drop policy if exists "clearance_stage_instances: student inserts for own request" on clearance_stage_instances;
create policy "clearance_stage_instances: student inserts for own request" on clearance_stage_instances
    for insert with check (
        exists (
            select 1 from clearance_requests cr
            join student_profiles sp on sp.id = cr.student_id
            where cr.id = clearance_request_id and sp.profile_id = (select auth.uid())
        )
    );
drop policy if exists "clearance_stage_instances: staff update assigned-role stages" on clearance_stage_instances;
create policy "clearance_stage_instances: staff update assigned-role stages" on clearance_stage_instances
    for update using (public.is_reviewer_for_stage(id));

drop policy if exists "clearance_requirements: any authenticated user can read" on clearance_requirements;
create policy "clearance_requirements: any authenticated user can read" on clearance_requirements
    for select using ((select auth.role()) = 'authenticated');
drop policy if exists "clearance_requirements: admin creates within own institution" on clearance_requirements;
create policy "clearance_requirements: admin creates within own institution" on clearance_requirements
    for insert with check (public.is_institution_admin_for(institution_id));

drop policy if exists "student_documents: read own or reviewable" on student_documents;
create policy "student_documents: read own or reviewable" on student_documents
    for select using (
        exists (select 1 from student_profiles sp where sp.id = student_id and sp.profile_id = (select auth.uid()))
        or public.is_reviewer_for_student(student_id)
    );

drop policy if exists "payment_records: student reads own" on payment_records;
drop policy if exists "payment_records: read own or reviewable" on payment_records;
create policy "payment_records: read own or reviewable" on payment_records
    for select using (
        exists (select 1 from student_profiles sp where sp.id = student_id and sp.profile_id = (select auth.uid()))
        or public.is_reviewer_for_student(student_id)
    );
-- Bursary staff manually acknowledge a payment made outside the app
-- (cash/bank transfer) — there's no payment gateway integrated.
drop policy if exists "payment_records: bursary staff can record for reviewable student" on payment_records;
create policy "payment_records: bursary staff can record for reviewable student" on payment_records
    for insert with check (
        exists (
            select 1 from profiles p
            where p.id = (select auth.uid()) and p.role = 'bursary' and p.status = 'active'
        )
        and public.is_reviewer_for_student(student_id)
    );

drop policy if exists "ai_chat_logs: user reads own" on ai_chat_logs;
create policy "ai_chat_logs: user reads own" on ai_chat_logs
    for select using ((select auth.uid()) = profile_id);
