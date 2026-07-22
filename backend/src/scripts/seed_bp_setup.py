"""
Seed script for PAC Business Plan Setup (Schedule, Guideline, Outlook).
Run: python src/scripts/seed_bp_setup.py
"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.database import async_engine, Base, get_db
from app.models.business_plan_setup import PACBusinessPlanSetup
from sqlalchemy import select


async def seed():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async for session in get_db():
        try:
            existing = await session.execute(select(PACBusinessPlanSetup).limit(1))
            if existing.scalars().first():
                print("Setup data already exists. Skipping seed.")
                return

            schedules = [
                {
                    "setup_module": "schedule",
                    "plan_year": 2024,
                    "content": {
                        "activities": [
                            {"no": 1, "activity": "Notification of 2024 business plan timeline", "date": "Sep 22", "day": "Friday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "ok", "remarks": "Timeline"},
                            {"no": 2, "activity": "Distribution of all relevant templates", "date": "Sep 29", "day": "Friday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "ok", "remarks": "CS"},
                            {"no": 3, "activity": "2024 economic outlook & guideline", "date": "Sep 29", "day": "Friday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Outlook Report"},
                            {"no": 4, "activity": "Review & discuss financial template with Company", "date": "Sep 30", "day": "Sunday", "sales": "F", "development": "F", "plant": "F", "admin": "F", "director": "x", "remarks": "Finance Team"},
                            {"no": 5, "activity": "Prepare sales plan & strategic direction", "date": "Oct 1", "day": "Tuesday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Business Plan"},
                            {"no": 6, "activity": "Business development plan : CMO, export and others", "date": "Oct 25-29", "day": "Tue-Thu", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "81, 82"},
                            {"no": 7, "activity": "Sales plan 2024 : by department, product & area", "date": "Oct 25", "day": "Wednesday", "sales": "x", "development": "$1, 52", "plant": "x", "admin": "x", "director": "x", "remarks": "Sales Plan"},
                            {"no": 8, "activity": "Starting sales plan with Stakeholders / HO review", "date": "Oct 28", "day": "Monday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "Petey", "remarks": "Petey"},
                            {"no": 9, "activity": "Purchase plan", "date": "Nov 1", "day": "Friday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Purchase"},
                            {"no": 10, "activity": "Reduction / manufacturing plan", "date": "Nov 12", "day": "Tuesday", "sales": "x", "development": "x", "plant": "x", "admin": "Now 14", "director": "x", "remarks": "Plant"},
                            {"no": 11, "activity": "Data evaluation : production, personnel, purchase, inventory, opex budget plan", "date": "Nov 23-24", "day": "Thu-Fri", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "Now 23", "remarks": "Budget Meeting"},
                            {"no": 12, "activity": "Forecasting : profit and loss simulation", "date": "Nov 24", "day": "Thursday", "sales": "x", "development": "x", "plant": "x", "admin": "Now 24", "director": "x", "remarks": "Finance"},
                            {"no": 13, "activity": "Final Budget decision", "date": "Dec 6", "day": "Wednesday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "Dec 6", "remarks": "Final"},
                            {"no": 14, "activity": "2024 Cashflow forecasting", "date": "Dec 6", "day": "Wednesday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Cashflow"},
                            {"no": 15, "activity": "2024 Business plan report", "date": "Dec 12", "day": "Wednesday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Report"},
                            {"no": 16, "activity": "Reporting business plan 2024 to President Director", "date": "Dec 12", "day": "Wednesday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "President Director"},
                        ]
                    },
                    "status": "final",
                },
                {
                    "setup_module": "schedule",
                    "plan_year": 2025,
                    "content": {
                        "activities": [
                            {"no": 1, "activity": "Notification of 2025 business plan timeline", "date": "Sep 20", "day": "Friday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "ok", "remarks": "Timeline"},
                            {"no": 2, "activity": "Distribution of all relevant templates", "date": "Sep 20", "day": "Friday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "ok", "remarks": "CS"},
                            {"no": 3, "activity": "2025 economic outlook & guideline", "date": "Sep 29", "day": "Friday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Outlook Report"},
                            {"no": 4, "activity": "Review financial template with Company", "date": "Sep 30", "day": "Sunday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Finance"},
                            {"no": 5, "activity": "Prepare sales plan & strategic direction", "date": "Oct 1", "day": "Tuesday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Plan"},
                            {"no": 6, "activity": "Business development plan : CMO, export and others", "date": "Oct 25-29", "day": "Tue-Thu", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "BD Plan"},
                            {"no": 7, "activity": "Sales plan 2025 : by department, product & area", "date": "Oct 25", "day": "Wednesday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Sales Plan"},
                            {"no": 8, "activity": "Starting sales plan with Stakeholders / HO review", "date": "Oct 28", "day": "Monday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Review"},
                            {"no": 9, "activity": "Purchase plan / reduction / manufacturing plan", "date": "Nov 1", "day": "Friday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Purchase/Manufacturing"},
                            {"no": 10, "activity": "Data evaluation : production, personnel, purchase, inventory, opex budget plan", "date": "Nov 23-24", "day": "Thu-Fri", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Budget Meeting"},
                            {"no": 11, "activity": "Forecasting : profit and loss simulation", "date": "Nov 24", "day": "Thursday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Finance"},
                            {"no": 12, "activity": "Final Budget decision", "date": "Dec 5", "day": "Friday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Final"},
                            {"no": 13, "activity": "2025 Cashflow forecasting", "date": "Dec 5", "day": "Friday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Cashflow"},
                            {"no": 14, "activity": "2025 Business plan report", "date": "Dec 12", "day": "Wednesday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Report"},
                            {"no": 15, "activity": "Reporting business plan 2025 to President Director", "date": "Dec 12", "day": "Wednesday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "President Director"},
                        ]
                    },
                    "status": "final",
                },
                {
                    "setup_module": "schedule",
                    "plan_year": 2026,
                    "content": {
                        "activities": [
                            {"no": 1, "activity": "Notification of 2026 business plan timeline", "date": "Sep 19", "day": "Friday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "ok", "remarks": "Timeline"},
                            {"no": 2, "activity": "Distribution of all relevant templates", "date": "Sep 19", "day": "Friday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "ok", "remarks": "CS"},
                            {"no": 3, "activity": "2026 economic outlook & guideline", "date": "Sep 29", "day": "Friday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Outlook Report"},
                            {"no": 4, "activity": "Review financial template with Company", "date": "Sep 30", "day": "Sunday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Finance"},
                            {"no": 5, "activity": "Prepare sales plan & strategic direction", "date": "Oct 1", "day": "Tuesday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Plan"},
                            {"no": 6, "activity": "Purchase plan", "date": "Oct 1", "day": "Monday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Purchase"},
                            {"no": 7, "activity": "Opex budget plan", "date": "Oct 1", "day": "Monday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Opex"},
                            {"no": 8, "activity": "Data evaluation & budget meeting with each Department", "date": "Nov 26-28", "day": "Tue-Thu", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Budget Meeting"},
                            {"no": 9, "activity": "Collecting & financing plan", "date": "Nov 28", "day": "Thursday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Finance"},
                            {"no": 10, "activity": "Other income & expenses", "date": "Nov 28", "day": "Thursday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Other"},
                            {"no": 11, "activity": "2026 cashflow forecasting", "date": "Nov 28", "day": "Thursday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Cashflow"},
                            {"no": 12, "activity": "2026 Business plan report", "date": "Dec 12", "day": "Wednesday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "Report"},
                            {"no": 13, "activity": "Reporting business plan 2026 to President Director", "date": "Dec 12", "day": "Wednesday", "sales": "x", "development": "x", "plant": "x", "admin": "x", "director": "x", "remarks": "President Director"},
                        ]
                    },
                    "status": "final",
                },
            ]

            guidelines = [
                {
                    "setup_module": "guideline",
                    "plan_year": 2024,
                    "content": {
                        "sections": [
                            {
                                "title": "1. Working Days",
                                "items": [
                                    {"label": "Jan", "value": 22}, {"label": "Feb", "value": 20}, {"label": "Mar", "value": 23},
                                    {"label": "Apr", "value": 21}, {"label": "May", "value": 22}, {"label": "Jun", "value": 20},
                                    {"label": "Jul", "value": 23}, {"label": "Aug", "value": 21}, {"label": "Sep", "value": 21},
                                    {"label": "Oct", "value": 23}, {"label": "Nov", "value": 19}, {"label": "Dec", "value": 20},
                                ],
                            },
                            {
                                "title": "2. Economic Indicator for Budgeting",
                                "items": [
                                    {"label": "Exchange Rate (IDR/USD)", "value": "15,000 - 15,100"},
                                    {"label": "Minimum Salary (UMR)", "value": "Rp 4,900,000"},
                                    {"label": "Inflation", "value": "2.7% - 2.8%"},
                                ],
                            },
                            {
                                "title": "3. Meeting & Business Trip",
                                "items": [
                                    {"label": "Domestic — Director", "value": "Rp 800,000 / day"},
                                    {"label": "Domestic — General Manager", "value": "Rp 700,000 / day"},
                                    {"label": "Domestic — Senior Manager", "value": "Rp 600,000 / day"},
                                    {"label": "Domestic — Manager", "value": "Rp 500,000 / day"},
                                    {"label": "Domestic — Staff", "value": "Rp 400,000 / day"},
                                    {"label": "International — Director", "value": "$300 / day"},
                                    {"label": "International — Manager", "value": "$200 / day"},
                                    {"label": "International — Staff", "value": "$150 / day"},
                                ],
                            },
                        ]
                    },
                    "status": "final",
                },
                {
                    "setup_module": "guideline",
                    "plan_year": 2025,
                    "content": {
                        "sections": [
                            {
                                "title": "1. Working Days",
                                "items": [
                                    {"label": "Jan", "value": 22}, {"label": "Feb", "value": 20}, {"label": "Mar", "value": 23},
                                    {"label": "Apr", "value": 21}, {"label": "May", "value": 22}, {"label": "Jun", "value": 20},
                                    {"label": "Jul", "value": 23}, {"label": "Aug", "value": 21}, {"label": "Sep", "value": 21},
                                    {"label": "Oct", "value": 23}, {"label": "Nov", "value": 19}, {"label": "Dec", "value": 20},
                                ],
                            },
                            {
                                "title": "2. Economic Indicator for Budgeting",
                                "items": [
                                    {"label": "Exchange Rate (IDR/USD)", "value": "15,200 - 16,000"},
                                    {"label": "Minimum Salary (UMR)", "value": "Rp 5,000,000"},
                                    {"label": "Inflation", "value": "2.5% - 2.7%"},
                                ],
                            },
                            {
                                "title": "3. Meeting & Business Trip",
                                "items": [
                                    {"label": "Domestic — Director", "value": "Rp 850,000 / day"},
                                    {"label": "Domestic — General Manager", "value": "Rp 750,000 / day"},
                                    {"label": "Domestic — Senior Manager", "value": "Rp 650,000 / day"},
                                    {"label": "Domestic — Manager", "value": "Rp 550,000 / day"},
                                    {"label": "Domestic — Staff", "value": "Rp 450,000 / day"},
                                    {"label": "International — Director", "value": "$350 / day"},
                                    {"label": "International — Manager", "value": "$250 / day"},
                                    {"label": "International — Staff", "value": "$180 / day"},
                                ],
                            },
                        ]
                    },
                    "status": "final",
                },
                {
                    "setup_module": "guideline",
                    "plan_year": 2026,
                    "content": {
                        "sections": [
                            {
                                "title": "1. Working Days",
                                "items": [
                                    {"label": "Jan", "value": 22}, {"label": "Feb", "value": 20}, {"label": "Mar", "value": 23},
                                    {"label": "Apr", "value": 21}, {"label": "May", "value": 22}, {"label": "Jun", "value": 20},
                                    {"label": "Jul", "value": 23}, {"label": "Aug", "value": 21}, {"label": "Sep", "value": 21},
                                    {"label": "Oct", "value": 23}, {"label": "Nov", "value": 19}, {"label": "Dec", "value": 20},
                                ],
                            },
                            {
                                "title": "2. Economic Indicator for Budgeting",
                                "items": [
                                    {"label": "Exchange Rate (IDR/USD)", "value": "15,200 - 16,000"},
                                    {"label": "Minimum Salary (UMR)", "value": "Rp 5,200,000"},
                                    {"label": "Inflation", "value": "2.5% - 3.0%"},
                                ],
                            },
                            {
                                "title": "3. Meeting & Business Trip",
                                "items": [
                                    {"label": "Domestic — Director", "value": "Rp 900,000 / day"},
                                    {"label": "Domestic — General Manager", "value": "Rp 800,000 / day"},
                                    {"label": "Domestic — Senior Manager", "value": "Rp 700,000 / day"},
                                    {"label": "Domestic — Manager", "value": "Rp 600,000 / day"},
                                    {"label": "Domestic — Staff", "value": "Rp 500,000 / day"},
                                    {"label": "International — Director", "value": "$400 / day"},
                                    {"label": "International — Manager", "value": "$300 / day"},
                                    {"label": "International — Staff", "value": "$220 / day"},
                                ],
                            },
                        ]
                    },
                    "status": "final",
                },
            ]

            outlooks = [
                {
                    "setup_module": "outlook",
                    "plan_year": 2024,
                    "content": {
                        "global_economic": {
                            "title": "I. Global Economic Outlook",
                            "items": [
                                {"label": "Global GDP Forecast", "value": "Decrease from 3.0% in 2023 to 2.7% in 2024"},
                                {"label": "Key Factor 1", "value": "Sharp slowdown in China — persistent Yuan weakness"},
                                {"label": "Key Factor 2", "value": "Declining inflation — reflecting drop in energy prices"},
                                {"label": "Key Factor 3", "value": "Russian invasion of Ukraine — ongoing recovery with OECD support"},
                                {"label": "Fed Interest Rate", "value": "5.5% (Sep 2023) -> Expected 5.7% Q4 2023 -> 5.5% in 2024"},
                                {"label": "Global Inflation", "value": "Projected to decline from 3.8% to 2.6% in 2024"},
                            ],
                        },
                        "indonesia_economic": {
                            "title": "II. Indonesia Economic Outlook",
                            "items": [
                                {"label": "GDP Forecast", "value": "5.1% in 2023 -> 5.2% in 2024"},
                                {"label": "Annual Budget", "value": "Income Rp 2.8 T + Financing Rp 0.5 T = Expense Rp 3.3 T"},
                                {"label": "Target", "value": "Accelerate inclusive and sustainable economic transformation"},
                                {"label": "Inflation", "value": "2.7% - 2.8%"},
                                {"label": "Interest Rate", "value": "6.0% - 6.9%"},
                                {"label": "Exchange Rate", "value": "IDR 15,000 - 15,100 / USD"},
                                {"label": "Geopolitics", "value": "Presidential election Feb 2024 — potential unstable economic condition"},
                                {"label": "IKN Capital", "value": "Move to Kalimantan (IKN) from 2024-2045"},
                            ],
                        },
                        "pharmaceutical": {
                            "title": "III. Pharmaceutical Industry",
                            "items": [
                                {"label": "Global Market Size", "value": "Expected $ 1.1 Trillion in 2023 to $ 1.2 Trillion in 2024"},
                                {"label": "Indonesia Growth Rate", "value": "Expected 12% in 2024"},
                                {"label": "TKDN Objective", "value": "Reduce importation of raw material by 24% in 2024"},
                                {"label": "Oncology", "value": "API for oncology still depend on import API"},
                                {"label": "CKD OTTO Strategy", "value": "Increasing TKDN score with local material purchase; Cooperate with foreign oncology medical worker"},
                            ],
                        },
                    },
                    "status": "final",
                },
                {
                    "setup_module": "outlook",
                    "plan_year": 2025,
                    "content": {
                        "global_economic": {
                            "title": "I. Global Economic Outlook",
                            "items": [
                                {"label": "Global GDP Forecast", "value": "Increase 0.1%p to 3.3% in 2025"},
                                {"label": "Key Factor 1", "value": "Cooling down War issue Israel-Hamas and Politics Russia-Ukraine"},
                                {"label": "Key Factor 2", "value": "Global inflation rate decrease from 5.9% in 2024 to 4.5% in 2025"},
                                {"label": "Fed Interest Rate", "value": "5.5% (Q2 2024), 5.0% (Q3 2024), expected 4.1% avg in 2025"},
                                {"label": "Global Inflation", "value": "Projected to decline to 4.5% in 2025"},
                                {"label": "Exchange Rate Forecast", "value": "IDR 15,715 -> 15,300 / USD"},
                            ],
                        },
                        "indonesia_economic": {
                            "title": "II. Indonesia Economic Outlook",
                            "items": [
                                {"label": "GDP Forecast", "value": "5.2% in 2025 (0.1%p from 2024)"},
                                {"label": "Annual Budget", "value": "Income IDR 3,005 T + Financing IDR 616 T = Expense IDR 3,621 T"},
                                {"label": "Target", "value": "Accelerate inclusive and sustainable economic growth"},
                                {"label": "Inflation", "value": "2.5% - 2.6%"},
                                {"label": "Interest Rate", "value": "7.0%"},
                                {"label": "Exchange Rate", "value": "IDR 16,000 / USD (Forecast 15,200)"},
                                {"label": "New Government", "value": "(2024-2029) Prabowo & Gibran — Continue Previous President's Objective"},
                                {"label": "Oil Price", "value": "USD 82-84 / barrel"},
                            ],
                        },
                        "pharmaceutical": {
                            "title": "III. Pharmaceutical Industry",
                            "items": [
                                {"label": "Global Sales", "value": "USD 1.5 Trillion in 2024 -> USD 1.6 Trillion in 2025"},
                                {"label": "Asia Sales", "value": "USD 484 Billion in 2024 -> USD 634 Billion in 2025"},
                                {"label": "Indonesia Sales", "value": "IDR 151 Trillion in 2024 -> IDR 161 Trillion in 2025"},
                                {"label": "Oncology Market", "value": "IDR 19 Trillion -> IDR 21 Trillion in 2025"},
                                {"label": "CKD OTTO Strategy", "value": "Increasing TKDN with local material; Cooperate with foreign oncology worker"},
                            ],
                        },
                    },
                    "status": "final",
                },
                {
                    "setup_module": "outlook",
                    "plan_year": 2026,
                    "content": {
                        "global_economic": {
                            "title": "I. Global Economic Outlook",
                            "items": [
                                {"label": "Global GDP Forecast", "value": "Moderate growth expected"},
                                {"label": "Key Factor", "value": "Post-covid recovery, energy prices stabilization"},
                                {"label": "Fed Interest Rate", "value": "Expected to stabilize around 4.0-4.5%"},
                                {"label": "Global Inflation", "value": "Returning to target levels 2-3%"},
                            ],
                        },
                        "indonesia_economic": {
                            "title": "II. Indonesia Economic Outlook",
                            "items": [
                                {"label": "GDP Forecast", "value": "5.3% projected"},
                                {"label": "Inflation", "value": "2.5% - 3.0%"},
                                {"label": "Exchange Rate", "value": "IDR 15,200 / USD forecast"},
                                {"label": "Focus", "value": "Infrastructure, IKN development, social programs"},
                            ],
                        },
                        "pharmaceutical": {
                            "title": "III. Pharmaceutical Industry",
                            "items": [
                                {"label": "Global Market", "value": "Continued growth driven by innovation and aging population"},
                                {"label": "Indonesia Market", "value": "Double-digit growth expected with TKDN push"},
                                {"label": "Oncology", "value": "Fastest growing segment; local API development priority"},
                            ],
                        },
                    },
                    "status": "draft",
                },
            ]

            for item in schedules + guidelines + outlooks:
                session.add(PACBusinessPlanSetup(**item))

            await session.commit()
            print(f"Seeded {len(schedules)} schedules, {len(guidelines)} guidelines, {len(outlooks)} outlooks")
            return
        except Exception as e:
            print(f"Seed error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


if __name__ == "__main__":
    asyncio.run(seed())
