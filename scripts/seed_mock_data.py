#!/usr/bin/env python

"""Populate the IPO database with realistic mock data for testing."""

from __future__ import annotations

import argparse
import os
import random
import secrets
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from werkzeug.security import generate_password_hash  # noqa: E402

from ipo_app import create_app  # noqa: E402
from ipo_app.extensions import db  # noqa: E402
from ipo_app.models import Student, Teacher, TeacherLanguage, TeacherMessageTemplate  # noqa: E402
from ipo_app.views import _ensure_teacher_portal_credentials  # noqa: E402


COUNTRY_DATA = {
    "United Kingdom": {
        "native": "English",
        "student_names": [
            ("Amelia", "Hughes"),
            ("Noah", "Chambers"),
            ("Harper", "Walters"),
            ("Ethan", "Reed"),
            ("Lily", "Osborne"),
            ("Jacob", "Fletcher"),
            ("Sophia", "Hayes"),
            ("Leo", "Gardner"),
            ("Isabella", "Potter"),
            ("Max", "Rowe"),
        ],
        "teacher_names": [
            ("Oliver", "Barrett"),
            ("Freya", "Jennings"),
            ("Isaac", "Thorpe"),
            ("Evie", "Macdonald"),
            ("Tom", "Spencer"),
            ("Zara", "Lamb"),
            ("Harrison", "Gibbs"),
            ("Poppy", "Norton"),
        ],
    },
    "United States": {
        "native": "English",
        "student_names": [
            ("Charlotte", "Bennett"),
            ("Logan", "Hayes"),
            ("Avery", "Sutton"),
            ("Mason", "Griffin"),
            ("Ella", "Parker"),
            ("Landon", "Harper"),
            ("Scarlett", "Ford"),
            ("Wyatt", "Hudson"),
            ("Aria", "Coleman"),
            ("Caleb", "Drake"),
        ],
        "teacher_names": [
            ("James", "Whitaker"),
            ("Mia", "Hammond"),
            ("Owen", "Dalton"),
            ("Evelyn", "Kerr"),
            ("Henry", "Abbott"),
            ("Nora", "Vaughn"),
            ("Dominic", "Sears"),
            ("Ruby", "Finch"),
        ],
    },
    "Canada": {
        "native": "English",
        "student_names": [
            ("Madeline", "Roy"),
            ("Grayson", "Bouchard"),
            ("Claire", "Tremblay"),
            ("Parker", "Gervais"),
            ("Violet", "Perreault"),
            ("Easton", "Lalonde"),
            ("Sadie", "Caron"),
            ("Micah", "Beaulieu"),
            ("Aurora", "Cormier"),
            ("Ryder", "Girard"),
        ],
        "teacher_names": [
            ("Elliot", "Fortin"),
            ("Hazel", "Gauvin"),
            ("Blake", "Pelletier"),
            ("Juliet", "Lamoureux"),
            ("Cole", "Desrosiers"),
            ("Stella", "Gauthier"),
            ("Declan", "O'Brien"),
            ("Naomi", "Belanger"),
        ],
    },
    "Australia": {
        "native": "English",
        "student_names": [
            ("Isla", "Lawson"),
            ("Cooper", "Abbey"),
            ("Matilda", "Quinn"),
            ("Archie", "Bowen"),
            ("Georgia", "Colson"),
            ("Finn", "Salter"),
            ("Willow", "Keating"),
            ("Jasper", "Ridley"),
            ("Savannah", "Hales"),
            ("Miles", "Carver"),
        ],
        "teacher_names": [
            ("Harvey", "Lowry"),
            ("Sienna", "Radcliffe"),
            ("Luca", "Trent"),
            ("Imogen", "Marley"),
            ("Flynn", "Kendall"),
            ("Eliza", "Thornton"),
            ("Beau", "Finley"),
            ("Alicia", "Newell"),
        ],
    },
    "Ireland": {
        "native": "English",
        "student_names": [
            ("Aoife", "Byrne"),
            ("Cian", "Farrell"),
            ("Niamh", "Keane"),
            ("Dara", "Sweeney"),
            ("Orla", "Doyle"),
            ("Ronan", "Lyons"),
            ("Ciara", "Brennan"),
            ("Sean", "Doherty"),
            ("Maeve", "Gallagher"),
            ("Eoin", "O'Rourke"),
        ],
        "teacher_names": [
            ("Padraig", "Mulcahy"),
            ("Saoirse", "Sheehan"),
            ("Fionn", "O'Callaghan"),
            ("Aine", "O'Leary"),
            ("Colm", "Shea"),
            ("Roisin", "Flynn"),
            ("Tiernan", "Boland"),
            ("Una", "Horgan"),
        ],
    },
    "Spain": {
        "native": "Spanish",
        "student_names": [
            ("Lucia", "Martinez"),
            ("Hugo", "Prieto"),
            ("Valeria", "Suarez"),
            ("Diego", "Crespo"),
            ("Blanca", "Morales"),
            ("Marcos", "Vargas"),
            ("Clara", "Herrera"),
            ("Sergio", "Castro"),
            ("Elena", "Paredes"),
            ("Pablo", "Benitez"),
        ],
        "teacher_names": [
            ("Carlos", "Marin"),
            ("Patricia", "Navarro"),
            ("Andres", "Santana"),
            ("Irene", "Valencia"),
            ("Manuel", "Rios"),
            ("Carla", "Coronado"),
            ("Jorge", "Lozano"),
            ("Nerea", "Mora"),
        ],
    },
    "Mexico": {
        "native": "Spanish",
        "student_names": [
            ("Renata", "Sandoval"),
            ("Emilio", "Ortega"),
            ("Camila", "Zamora"),
            ("Mateo", "Delgado"),
            ("Abril", "Esquivel"),
            ("Thiago", "Galvez"),
            ("Julieta", "Pineda"),
            ("Diego", "Ayala"),
            ("Mariana", "Solano"),
            ("Luis", "Barrios"),
        ],
        "teacher_names": [
            ("Alejandro", "Cardenas"),
            ("Daniela", "Trejo"),
            ("Rafael", "Velasco"),
            ("Ximena", "Bustamante"),
            ("Fernando", "Guzman"),
            ("Itzel", "Corona"),
            ("Santiago", "Cedillo"),
            ("Paola", "Villalobos"),
        ],
    },
    "Argentina": {
        "native": "Spanish",
        "student_names": [
            ("Malena", "Dominguez"),
            ("Bruno", "Rosales"),
            ("Catalina", "Paz"),
            ("Lautaro", "Blanco"),
            ("Emilia", "Quiroga"),
            ("Ignacio", "Peralta"),
            ("Mora", "Gallardo"),
            ("Ramiro", "Ibanez"),
            ("Aitana", "Roldan"),
            ("Tomas", "Merino"),
        ],
        "teacher_names": [
            ("Gonzalo", "Ferreyra"),
            ("Julieta", "Miranda"),
            ("Facundo", "Segura"),
            ("Martina", "Lima"),
            ("Nicolas", "Maidana"),
            ("Rocio", "Acosta"),
            ("Esteban", "Saez"),
            ("Selena", "Bustillo"),
        ],
    },
    "Chile": {
        "native": "Spanish",
        "student_names": [
            ("Antonia", "Barra"),
            ("Vicente", "Farias"),
            ("Florencia", "Mella"),
            ("Matias", "Vergara"),
            ("Josefa", "Arancibia"),
            ("Cristobal", "Baeza"),
            ("Isidora", "Navarrete"),
            ("Benjamin", "Salinas"),
            ("Constanza", "Carreno"),
            ("Lucas", "Pezoa"),
        ],
        "teacher_names": [
            ("Sebastian", "Escobar"),
            ("Camila", "Figueroa"),
            ("Mauricio", "Tapia"),
            ("Daniela", "Cardozo"),
            ("Alonso", "Contreras"),
            ("Fernanda", "Bustamante"),
            ("Javier", "Tobar"),
            ("Valentina", "Prado"),
        ],
    },
    "Colombia": {
        "native": "Spanish",
        "student_names": [
            ("Sara", "Bermudez"),
            ("Juan", "Villamil"),
            ("Luciana", "Lizarazo"),
            ("Felipe", "Coronel"),
            ("Juliana", "Gaviria"),
            ("Simon", "Bayona"),
            ("Valentina", "Saavedra"),
            ("Emmanuel", "Quinones"),
            ("Danna", "Salamanca"),
            ("Jeronimo", "Zapata"),
        ],
        "teacher_names": [
            ("Camilo", "Perdomo"),
            ("Laura", "Hoyos"),
            ("Andres", "Murcia"),
            ("Paula", "Serna"),
            ("Oscar", "Lagos"),
            ("Julieta", "Barbosa"),
            ("Jorge", "Carranza"),
            ("Tatiana", "Bernal"),
        ],
    },
    "France": {
        "native": "French",
        "student_names": [
            ("Ines", "Morel"),
            ("Louis", "Dufour"),
            ("Camille", "Lemoine"),
            ("Arthur", "Monet"),
            ("Lena", "Faure"),
            ("Theo", "Renault"),
            ("Zoe", "Picard"),
            ("Rayan", "Boucher"),
            ("Anna", "Rousseau"),
            ("Mathis", "Garnier"),
        ],
        "teacher_names": [
            ("Hugo", "Leclerc"),
            ("Claire", "Giroux"),
            ("Adrien", "Bodin"),
            ("Lea", "Germain"),
            ("Nathan", "Perrot"),
            ("Mae", "Verdier"),
            ("Victor", "Barbier"),
            ("Salome", "Gaillard"),
        ],
    },
    "Belgium": {
        "native": "French",
        "student_names": [
            ("Elise", "Delvaux"),
            ("Noah", "Cuvelier"),
            ("Axelle", "Masson"),
            ("Jules", "Dubray"),
            ("Gwen", "Bailly"),
            ("Loic", "Hanot"),
            ("Sarah", "Jonet"),
            ("Mael", "Paquet"),
            ("Lucie", "Ledoux"),
            ("Nael", "Severin"),
        ],
        "teacher_names": [
            ("Amaury", "Fevre"),
            ("Manon", "Seilles"),
            ("Quentin", "Braun"),
            ("Adele", "Collard"),
            ("Bastien", "Maquet"),
            ("Roxane", "Langlois"),
            ("Maxime", "Desmet"),
            ("Solene", "Remy"),
        ],
    },
    "Canada (Quebec)": {
        "native": "French",
        "student_names": [
            ("Emilie", "Larocque"),
            ("Olivier", "Gagnier"),
            ("Maude", "Tessier"),
            ("Xavier", "Nolin"),
            ("Rosalie", "Descoteaux"),
            ("Antoine", "Labonte"),
            ("Florence", "Poisson"),
            ("Jeremie", "Thibault"),
            ("Camille", "Berube"),
            ("Cedric", "Plamondon"),
        ],
        "teacher_names": [
            ("Mathieu", "Perreault"),
            ("Ariane", "Duchesne"),
            ("Philippe", "Lebeau"),
            ("Maika", "Riendeau"),
            ("Jerome", "Lazure"),
            ("Elodie", "Delorme"),
            ("Simon", "Tremble"),
            ("Alyson", "Cloutier"),
        ],
    },
    "Switzerland": {
        "native": "French",
        "student_names": [
            ("Aline", "Favre"),
            ("Noe", "Baumann"),
            ("Mila", "Donnay"),
            ("Kilian", "Rieder"),
            ("Livia", "Fankhauser"),
            ("Yann", "Michel"),
            ("Tessa", "Hofmann"),
            ("Lois", "Aubert"),
            ("Anais", "Sutter"),
            ("Mael", "Vonlanthen"),
        ],
        "teacher_names": [
            ("Lionel", "Droz"),
            ("Cynthia", "Blaser"),
            ("Theo", "Burlet"),
            ("Celeste", "Gilliard"),
            ("Bastien", "Berthoud"),
            ("Claire", "Petitpierre"),
            ("Adrian", "Cuenat"),
            ("Nina", "Dalphin"),
        ],
    },
    "Luxembourg": {
        "native": "French",
        "student_names": [
            ("Maelys", "Decker"),
            ("Adrian", "Klein"),
            ("Leonie", "Schmit"),
            ("Noe", "Hoffmann"),
            ("Inaya", "Michel"),
            ("Tom", "Schroeder"),
            ("Naelle", "Weber"),
            ("Jonas", "Hartmann"),
        ],
        "teacher_names": [
            ("Etienne", "Kavanaugh"),
            ("Lara", "Faber"),
            ("Joel", "Kremer"),
            ("Lena", "Backes"),
            ("Lucas", "Braband"),
            ("Zelia", "Glod"),
            ("Ewan", "Schreiner"),
            ("Lilou", "Heinen"),
        ],
    },
    "Germany": {
        "native": "German",
        "student_names": [
            ("Mia", "Hoffmann"),
            ("Lukas", "Berger"),
            ("Johanna", "Kraus"),
            ("Finn", "Schuster"),
            ("Helena", "Brandt"),
            ("Jonas", "Metzger"),
            ("Leonie", "Ritter"),
            ("Noah", "Kunz"),
            ("Greta", "Ulrich"),
            ("Leon", "Voigt"),
        ],
        "teacher_names": [
            ("Felix", "Becker"),
            ("Marlene", "Jung"),
            ("Sebastian", "Arnold"),
            ("Clara", "Pfeiffer"),
            ("Daniel", "Weiss"),
            ("Hannah", "Zimmer"),
            ("Tobias", "Kolb"),
            ("Paula", "Lorenz"),
        ],
    },
    "Austria": {
        "native": "German",
        "student_names": [
            ("Elena", "Wagner"),
            ("Niklas", "Haas"),
            ("Sofie", "Berger"),
            ("Fabian", "Seidl"),
            ("Lena", "Mohr"),
            ("Jakob", "Neumeier"),
            ("Valentina", "Auer"),
            ("Samuel", "Ebner"),
            ("Theresa", "Gabler"),
            ("Julian", "Schindler"),
        ],
        "teacher_names": [
            ("Max", "Hutter"),
            ("Lisa", "Fellner"),
            ("Dominik", "Leitner"),
            ("Nina", "Beranek"),
            ("Stefan", "Haberl"),
            ("Carina", "Mandl"),
            ("Patrick", "Fischer"),
            ("Eva", "Stadlober"),
        ],
    },
    "Switzerland (German)": {
        "native": "German",
        "student_names": [
            ("Nora", "Imhof"),
            ("Simon", "Zeller"),
            ("Alina", "Widmer"),
            ("Tim", "Suter"),
            ("Mira", "Leuenberger"),
            ("Jan", "Rath"),
            ("Selina", "Vogel"),
            ("Noel", "Kaufmann"),
            ("Kim", "Bayer"),
            ("Lars", "Wettstein"),
        ],
        "teacher_names": [
            ("Raphael", "Schaller"),
            ("Larissa", "Steiger"),
            ("Joel", "Egger"),
            ("Mila", "Baumgartner"),
            ("Adrian", "Hauser"),
            ("Sabine", "Bischof"),
            ("Oliver", "Boller"),
            ("Annika", "Stutz"),
        ],
    },
    "Liechtenstein": {
        "native": "German",
        "student_names": [
            ("Alessia", "Kaiser"),
            ("Leonard", "Nigg"),
            ("Melina", "Beck"),
            ("Lorenz", "Schmid"),
            ("Mara", "Walser"),
            ("Jon", "Quaderer"),
            ("Marlene", "Gassner"),
            ("Fabio", "Lampert"),
        ],
        "teacher_names": [
            ("Marco", "Lingg"),
            ("Sabrina", "Sutter"),
            ("Pascal", "Frommelt"),
            ("Larissa", "Matt"),
            ("Gregor", "Meier"),
            ("Helena", "Heeb"),
            ("Patrick", "Vogt"),
            ("Tanja", "Marxer"),
        ],
    },
}


MEAL_PREFERENCES = ["No preference", "Vegetarian", "Vegan"]

STUDENT_LANGUAGE_DISTRIBUTION = {
    "English": 0.50,
    "Spanish": 0.20,
    "French": 0.15,
    "German": 0.15,
}

TEACHER_LANGUAGE_TARGETS = {
    "Spanish": 0.30,
    "French": 0.30,
    "German": 0.30,
}

TEACHER_ENGLISH_SHARE = 0.90

DEFAULT_MESSAGE_TEMPLATES = [
    {
        "name": "Request teacher to change room",
        "title": "Teacher needed in another room",
        "body": "{teacher_name}, please proceed to {room} for essay assessment.",
        "category": "Logistics",
    },
    {
        "name": "Collect essay from logistics desk",
        "title": "Essay collection needed",
        "body": "{teacher_name}, a new essay is ready for you at the logistics desk.",
        "category": "Logistics",
    },
    {
        "name": "Stage briefing reminder",
        "title": "Stage briefing reminder",
        "body": "Teachers assigned to Stage {stage_number}, please gather in briefing room {room} at {time}.",
        "category": "Briefing",
    },
    {
        "name": "Scoring deadline reminder",
        "title": "Reminder: scoring deadline approaching",
        "body": "Please ensure your outstanding essays are scored before {deadline}.",
        "category": "Schedule",
    },
]

_teacher_email_counts: dict[str, int] = {}
_student_email_counts: dict[str, int] = {}
_student_username_set: set[str] = set()
_seed_teacher_credentials: list[tuple[str, str, str]] = []


def _generate_seed_username(entry: dict, index: int) -> str:
    base = f"stu{_slugify(entry['last'])[:8]}{index:03d}"
    while base in _student_username_set:
        base = f"stu{secrets.token_hex(3)}"
    _student_username_set.add(base)
    return base


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_value.lower())


def _unique_email(base: str, domain: str, cache: dict[str, int]) -> str:
    count = cache.get(base, 0)
    cache[base] = count + 1
    if count == 0:
        return f"{base}@{domain}"
    return f"{base}{count}@{domain}"


def create_teacher(entry: dict, languages: list[str], index: int) -> Teacher:
    base = f"{_slugify(entry['first'])}.{_slugify(entry['last'])}"
    email = _unique_email(base, "ipo.ts", _teacher_email_counts)
    veteran_level = random.choice([1, 2, 3]) if random.random() < 0.7 else 0
    teacher = Teacher(
        first_name=entry["first"],
        last_name=entry["last"],
        email=email,
        country=entry["country"],
        school=f"{entry['country']} National School",
        gender="Male" if index % 2 == 0 else "Female",
        languages=", ".join(languages),
        meal_preference=MEAL_PREFERENCES[index % len(MEAL_PREFERENCES)],
        special_needs=None,
        tshirt_size=["S", "M", "L", "XL"][index % 4],
        delegation_leader=index % 8 == 0,
        prior_ipo_assessor_level=veteran_level,
        prior_ipo_assessor=bool(veteran_level),
        is_absent=False,
    )
    teacher.language_entries = [TeacherLanguage(language=lang) for lang in languages]
    return teacher


def create_student(entry: dict, language: str, index: int) -> Student:
    base = f"{_slugify(entry['first'])}.{_slugify(entry['last'])}"
    email = _unique_email(base, "school.ts", _student_email_counts)
    birth_year = 2006 if index % 2 == 0 else 2005
    student = Student(
        first_name=entry["first"],
        last_name=entry["last"],
        email=email,
        country=entry["country"],
        school=f"{entry['country']} College",
        gender="Male" if index % 2 == 0 else "Female",
        date_of_birth=date(birth_year, (index % 12) + 1, ((index % 20) + 1)),
        essay_language=language,
        keyboard_preference="AZERTY" if language == "French" else "QWERTY",
        meal_preference=MEAL_PREFERENCES[index % len(MEAL_PREFERENCES)],
        special_needs=None,
        is_absent=False,
    )
    return student


def build_entries(kind: str) -> list[dict]:
    records: list[dict] = []
    for country, data in COUNTRY_DATA.items():
        names = data["teacher_names" if kind == "teacher" else "student_names"]
        for first, last in names:
            records.append({
                "first": first,
                "last": last,
                "country": country,
                "native": data["native"],
            })
    return records


def seed_teachers() -> int:
    _seed_teacher_credentials.clear()
    entries = build_entries("teacher")
    random.shuffle(entries)

    teacher_configs = [
        {
            "data": entry,
            "languages": {entry["native"]},
        }
        for entry in entries
    ]

    total = len(teacher_configs)
    english_target = int(round(total * TEACHER_ENGLISH_SHARE))
    english_count = sum(1 for cfg in teacher_configs if "English" in cfg["languages"])

    non_english_teachers = [cfg for cfg in teacher_configs if "English" not in cfg["languages"]]
    for cfg in non_english_teachers:
        if english_count >= english_target:
            break
        cfg["languages"].add("English")
        english_count += 1

    for language, share in TEACHER_LANGUAGE_TARGETS.items():
        target = int(round(total * share))
        current = sum(1 for cfg in teacher_configs if language in cfg["languages"])
        candidates = [
            cfg for cfg in teacher_configs
            if language not in cfg["languages"] and cfg["data"]["native"] != language
        ]
        random.shuffle(candidates)
        for cfg in candidates:
            if current >= target:
                break
            cfg["languages"].add(language)
            current += 1

    for index, cfg in enumerate(teacher_configs):
        languages = sorted(cfg["languages"], key=lambda lang: (lang != cfg["data"]["native"], lang))
        teacher = create_teacher(cfg["data"], languages, index)
        db.session.add(teacher)
        username, plain_password = _ensure_teacher_portal_credentials(teacher, reset_password=True)
        if plain_password:
            _seed_teacher_credentials.append(
                (f"{teacher.first_name} {teacher.last_name}", username, plain_password)
            )

    return total


def seed_students(target: int = 90) -> int:
    entries = build_entries("student")
    random.shuffle(entries)

    targets: dict[str, int] = {}
    remaining = target
    languages = list(STUDENT_LANGUAGE_DISTRIBUTION.items())
    for language, share in languages[:-1]:
        count = int(round(target * share))
        count = min(count, remaining)
        targets[language] = count
        remaining -= count
    last_language = languages[-1][0]
    targets[last_language] = remaining

    assigned = []
    pool = entries[:]

    for language, count in targets.items():
        taken = 0
        idx = 0
        while taken < count:
            if idx >= len(pool):
                raise ValueError(f"Not enough students available to assign language {language}")
            candidate = pool[idx]
            if candidate["native"] == language:
                idx += 1
                continue
            pool.pop(idx)
            assigned.append((candidate, language))
            taken += 1

    students_created = 0
    for index, (entry, language) in enumerate(assigned):
        student = create_student(entry, language, index)
        student.upload_username = _generate_seed_username(entry, index)
        raw_password = f"{random.randint(1000, 9999)}{random.randint(1000, 9999)}"
        student.upload_password_hash = generate_password_hash(raw_password)
        student.upload_token = raw_password
        student.uploaded_filename = None
        student.uploaded_at = None
        student.__dict__["_seed_password_plain"] = raw_password
        db.session.add(student)
        students_created += 1

    return students_created


def ensure_message_templates() -> int:
    existing_names = {template.name for template in TeacherMessageTemplate.query.all()}
    created = 0
    for data in DEFAULT_MESSAGE_TEMPLATES:
        if data["name"] in existing_names:
            continue
        template = TeacherMessageTemplate(
            name=data["name"],
            title=data["title"],
            body=data["body"],
            category=data.get("category"),
        )
        db.session.add(template)
        created += 1
    if created:
        db.session.commit()
    return created


def reset_database() -> None:
    db.drop_all()
    db.create_all()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the IPO database with mock data.")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate database tables before seeding.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Seed even if existing records are present.",
    )
    parser.add_argument(
        "--students",
        type=int,
        default=90,
        help="Number of student records to create (default: 90).",
    )
    args = parser.parse_args()

    random.seed(42)

    app = create_app()
    with app.app_context():
        if args.reset:
            reset_database()
        else:
            db.create_all()

        if not args.force:
            if Student.query.count() > 0 or Teacher.query.count() > 0:
                print("Database already contains data. Use --force to seed anyway or --reset to start fresh.")
                return

        Student.query.delete()
        TeacherLanguage.query.delete()
        Teacher.query.delete()
        db.session.commit()

        teachers = seed_teachers()
        students = seed_students(args.students)
        db.session.commit()

        templates_created = ensure_message_templates()

        print(f"Seeded {teachers} teachers and {students} students.")
        if templates_created:
            print(f"Ensured {templates_created} message templates.")
        if _seed_teacher_credentials:
            print("Sample teacher portal credentials (first 5 teachers):")
            for name, username, password in _seed_teacher_credentials[:5]:
                print(f"  {name}: {username} / {password}")
        print("Sample student credentials (first 5 non-absent students):")
        for student in Student.query.filter_by(is_absent=False).limit(5).all():
            raw_password = getattr(student, "_seed_password_plain", "<hashed>")
            print(f"  {student.first_name} {student.last_name}: {student.upload_username} / {raw_password}")


if __name__ == "__main__":
    main()
