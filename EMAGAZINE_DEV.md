# E-Magazine Dynamic Viewer — Development Guide

## Overview
Transformasi PDF e-magazine statis menjadi web-based aplikasi interaktif dengan:
- Page-flip navigation
- Full-text search
- Interactive hotspots (clickable areas)
- QR code & sharing
- Analytics tracking
- Database-driven content

## Project Structure

```
backend/
├── app/
│   ├── models/
│   │   └── emagazine.py          # SQLAlchemy models
│   ├── routers/
│   │   ├── emagazine.py          # FastAPI endpoints
│   │   └── emagazine_hotspots.py # Hotspot CRUD endpoints
│   ├── utils/
│   │   └── pdf_parser.py         # PDF parsing utility
│   └── main.py                    # Router registration
├── emagazine_archive/            # Uploaded PDFs stored here
└── docker-compose.yml

frontend/
├── src/
│   ├── pages/
│   │   ├── EMagazinePage.jsx     # Main e-magazine viewer
│   │   └── admin/
│   │       └── EMagazineAdminPage.jsx # Admin dashboard
│   ├── components/
│   │   ├── emagazine/            # Viewer components
│   │   ├── admin/                # Admin components
│   │   └── ui/                   # Shared UI components
│   ├── stores/
│   │   └── emagazineStore.js     # Zustand state management
│   └── utils/
│       └── emagazineApi.js       # API client
```

## Database Schema

### Tables Created
1. **emagazine_editions** — Magazine versions/editions
2. **emagazine_content** — Extracted page content (searchable)
3. **emagazine_hotspots** — Clickable areas with actions
4. **emagazine_analytics** — User interaction tracking

### Indexes
- Full-text search on `emagazine_content.searchable_text`
- Composite indexes for edition + page lookups
- User analytics tracking indexes

## Setup Instructions

### 1. Create Database Tables
```bash
cd backend
python -c "
from app.database import Base, async_engine
import app.models.emagazine  # Import to register models
import asyncio

async def init():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('✅ E-magazine tables created successfully!')

asyncio.run(init())
"
```

### 2. Backend Setup
```bash
cd backend

# Install dependencies (if needed)
pip install -r requirements.txt

# Start backend server
python -m uvicorn app.main:app --reload --port 8001
```

### 3. Frontend Setup
```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev  # Runs on http://localhost:3000
```

## API Endpoints

All endpoints prefixed with `/api/emagazine`

### List Editions
```bash
GET /editions
```

### Get Single Page
```bash
GET /editions/{edition_id}/pages/{page_num}
```

### Search Content
```bash
POST /search
Content-Type: application/json

{
  "query": "birthday",
  "edition_id": 1
}
```

### Get Table of Contents
```bash
GET /editions/{edition_id}/toc
```

### Track Analytics
```bash
POST /analytics?edition_id=1
Content-Type: application/json

{
  "action_type": "page_view",
  "page_number": 5,
  "metadata": {"device": "mobile"}
}
```

### Analytics Summary
```bash
GET /analytics/{edition_id}/summary
```

### Upload New Edition (Phase 4.2)
```bash
POST /editions/upload
Content-Type: multipart/form-data

Form Fields:
- title: string
- edition_number: integer
- published_date: string (YYYY-MM-DD)
- file: PDF file

Response:
{
  "id": 2,
  "title": "CKD OTTO E-Magazine 4th Edition",
  "edition_number": 4,
  "published_date": "2026-09-02",
  "total_pages": 216,
  "created_at": "2026-09-02T10:30:00",
  "message": "Edition uploaded successfully. 216 pages parsed and indexed."
}
```

### Hotspot Endpoints

#### Get All Hotspots for Edition
```bash
GET /hotspots/editions/{edition_id}
```

#### Get Hotspots for Page
```bash
GET /hotspots/editions/{edition_id}/pages/{page_num}
```

#### Create Hotspot
```bash
POST /hotspots
Content-Type: application/json

{
  "edition_id": 1,
  "page_number": 5,
  "x_pos": 100,
  "y_pos": 150,
  "width": 200,
  "height": 80,
  "action_type": "contact",
  "action_data": {
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "+62-123-4567"
  },
  "tooltip": "Click for contact"
}
```

#### Update Hotspot
```bash
PUT /hotspots/{id}
Content-Type: application/json

{
  "tooltip": "Updated tooltip"
}
```

#### Delete Hotspot
```bash
DELETE /hotspots/{id}
```

## Development Phases

### ✅ Phase 1: Backend Foundation (COMPLETED)
- Database schema with PostgreSQL
- SQLAlchemy models
- Backend API endpoints
- Full-text search capability
- Analytics tracking infrastructure

### ✅ Phase 2: Frontend Viewer (COMPLETED)
- Frontend E-Magazine Viewer Component
- Page-by-page navigation
- Search interface with results
- Table of contents sidebar
- Responsive design
- State management with Zustand
- API integration

### ✅ Phase 3: Interactive Hotspots (COMPLETED)
- Backend hotspot management API
- Interactive modals (Contact, Link, Video, etc)
- Hotspot SVG overlay layer
- QR code generation
- Analytics tracking for hotspot clicks

### ✅ Phase 4: Admin Interface (COMPLETED)
- HotspotManager with CRUD operations
- AnalyticsDashboard with KPIs and charts
- EditionUploader (placeholder)
- Tabbed admin interface

### ✅ Phase 4.2: PDF Upload & Visual Editor (COMPLETED)
- Backend PDF upload endpoint with auto-parsing
- Visual hotspot editor (click-drag-create, resize, delete)
- EditionUploader with real upload functionality
- Visual feedback for hotspot creation and editing
- Integration with HotspotManager

## Frontend Structure

### Directory Layout
```
frontend/src/
├── pages/
│   ├── EMagazinePage.jsx              # Main viewer page
│   └── admin/
│       └── EMagazineAdminPage.jsx    # Admin dashboard
├── components/
│   ├── emagazine/
│   │   ├── NavigationBar.jsx         # Top nav
│   │   ├── PageViewer.jsx            # Content display
│   │   ├── SearchBar.jsx             # Search interface
│   │   ├── TableOfContents.jsx       # Sidebar TOC
│   │   ├── HotspotLayer.jsx          # SVG overlay
│   │   ├── HotspotEditor.jsx         # Visual editor
│   │   ├── Modal.jsx                 # Base modal
│   │   ├── ContactModal.jsx          # Contact modal
│   │   ├── LinkModal.jsx             # Link modal
│   │   └── VideoModal.jsx            # Video modal
│   ├── admin/
│   │   ├── HotspotManager.jsx        # CRUD interface
│   │   ├── AnalyticsDashboard.jsx    # Analytics
│   │   └── EditionUploader.jsx       # Upload form
│   └── ui/
│       └── Tabs.jsx                  # Tabbed nav
├── stores/
│   └── emagazineStore.js             # Zustand state
└── utils/
    └── emagazineApi.js               # API client
```

### State Management (Zustand)
```javascript
useEMagazineStore()
├── State:
│   ├── currentEditionId
│   ├── currentPage
│   ├── totalPages
│   ├── searchQuery
│   ├── searchResults[]
│   ├── tableOfContents{}
│   ├── showSidebar
│   └── showSearch
└── Actions:
    ├── setCurrentEdition(id)
    ├── setCurrentPage(page)
    ├── nextPage() / prevPage()
    └── ...
```

## Component Details

### EMagazinePage
Main viewer component with:
- Navigation bar (previous/next/go to page)
- Page viewer with content display
- Hotspot layer with interactive areas
- Search interface
- Table of contents sidebar
- Analytics tracking

### EMagazineAdminPage
Admin dashboard with three tabs:
1. **Hotspots** - CRUD with list and visual editor modes
2. **Analytics** - KPI cards and charts
3. **Editions** - Upload new PDFs

### HotspotEditor
Visual hotspot creation and editing:
- Click-and-drag to create hotspots
- Drag to move, resize corner to scale
- Delete button for each hotspot
- Page selector for multi-page editing
- Active hotspot list with action type indicator

### AnalyticsDashboard
Analytics visualization:
- KPI cards (total views, unique users, avg views)
- Bar chart of popular pages
- Engagement metrics grid
- Insights with recommendations

## Testing

### Prerequisites
1. PostgreSQL running
2. Backend tables created
3. Backend server running on port 8001
4. Frontend dev server running on port 3000

### Manual Testing Flow

1. **Navigate to E-Magazine Viewer**
   - http://localhost:3000/emagazine
   - Should load first edition automatically

2. **Test Navigation**
   - Click Previous/Next buttons
   - Input page number and press Enter
   - Verify page content changes

3. **Test Search**
   - Click Search icon
   - Type search term
   - Verify results appear with snippets

4. **Test Hotspots**
   - Hover over hotspot → see tooltip
   - Click hotspot → modal opens
   - Verify correct action type displayed

5. **Test Admin Interface**
   - Navigate to http://localhost:3000/admin/emagazine
   - Try uploading a PDF file
   - Create hotspots with visual editor
   - Check analytics dashboard

## Troubleshooting

### PDF Parser Not Found
```bash
apt-get install -y poppler-utils
```

### Database Connection Error
Ensure PostgreSQL is running and `.env` has correct credentials

### Missing Dependencies
```bash
pip install -r requirements.txt
npm install
```

## Next Steps

- Implement form hotspot type
- Add drag-and-drop file upload
- Performance optimization for large PDFs
- Production deployment setup

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy Async](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [React Documentation](https://react.dev/)
- [Zustand Documentation](https://github.com/pmndrs/zustand)
- [PostgreSQL Full-Text Search](https://www.postgresql.org/docs/current/textsearch.html)
