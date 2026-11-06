-- Supabase SQL Editor에서 실행하세요. 아래 관리자 UUID를 실제 본인의 Auth 사용자 UID로 교체해야 합니다.
create table if not exists public.diagnosis_reviews (
 id bigint generated always as identity primary key,
 created_at timestamptz not null default now(),
 product_name text not null check (char_length(product_name) between 1 and 120),
 purpose text not null,
 power_modes text[] not null,
 voltage text,
 wireless text,
 wireless_type text,
 charge_mode text,
 emc_status text not null,
 safety_status text not null,
 radio_status text not null,
 constraint review_only check (emc_status like '%확인 필요%' or safety_status like '%확인 필요%' or radio_status like '%확인 필요%')
);
alter table public.diagnosis_reviews enable row level security;
revoke all on public.diagnosis_reviews from anon, authenticated;
grant insert on public.diagnosis_reviews to anon;
grant select on public.diagnosis_reviews to authenticated;
-- 익명 사용자는 확인 필요 사례만 INSERT할 수 있고 SELECT는 불가능합니다.
drop policy if exists diagnosis_public_insert on public.diagnosis_reviews;
create policy diagnosis_public_insert on public.diagnosis_reviews for insert to anon with check (true);
-- 반드시 아래 UUID를 실제 관리자 Auth UID로 바꾸세요.
drop policy if exists diagnosis_admin_select on public.diagnosis_reviews;
create policy diagnosis_admin_select on public.diagnosis_reviews for select to authenticated using (auth.uid() = '00000000-0000-0000-0000-000000000000'::uuid);
-- 실제 관리자 UUID를 설정하기 전에는 관리자 조회가 차단됩니다.
