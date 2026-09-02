import React, { useState, useEffect } from 'react';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { Eye, Users, TrendingUp, Search } from 'lucide-react';
import emagazineAPI from '../../utils/emagazineApi';

export default function AnalyticsDashboard({ editionId }) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadAnalytics();
  }, [editionId]);

  const loadAnalytics = async () => {
    if (!editionId) return;
    setLoading(true);
    try {
      const data = await emagazineAPI.getAnalyticsSummary(editionId);
      setSummary(data);
    } catch (error) {
      console.error('Error loading analytics:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="text-center py-8">Loading analytics...</div>;
  }

  if (!summary) {
    return (
      <div className="text-center py-8 bg-gray-50 rounded-lg">
        <p className="text-gray-600">No analytics data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KPICard
          title="Total Page Views"
          value={summary.total_page_views || 0}
          icon={<Eye size={24} />}
          color="blue"
        />
        <KPICard
          title="Unique Users"
          value={summary.unique_users || 0}
          icon={<Users size={24} />}
          color="purple"
        />
        <KPICard
          title="Avg Views per User"
          value={
            summary.unique_users > 0
              ? (summary.total_page_views / summary.unique_users).toFixed(1)
              : 0
          }
          icon={<TrendingUp size={24} />}
          color="green"
        />
      </div>

      {/* Popular Pages Chart */}
      {summary.popular_pages && summary.popular_pages.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <h3 className="text-lg font-bold text-gray-900 mb-4">Popular Pages</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={summary.popular_pages}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="page" label={{ value: 'Page Number', position: 'insideBottom', offset: -5 }} />
              <YAxis label={{ value: 'Views', angle: -90, position: 'insideLeft' }} />
              <Tooltip />
              <Bar dataKey="views" fill="#3b82f6" name="Views" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Engagement Metrics */}
      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <h3 className="text-lg font-bold text-gray-900 mb-4">Engagement Metrics</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MetricBox
            label="Pages with Views"
            value={summary.popular_pages ? summary.popular_pages.length : 0}
          />
          <MetricBox
            label="Avg Page Views"
            value={
              summary.popular_pages && summary.popular_pages.length > 0
                ? (
                    summary.popular_pages.reduce((sum, p) => sum + p.views, 0) /
                    summary.popular_pages.length
                  ).toFixed(1)
                : 0
            }
          />
          <MetricBox
            label="Most Popular Page"
            value={
              summary.popular_pages && summary.popular_pages.length > 0
                ? `Page ${summary.popular_pages[0].page}`
                : '-'
            }
          />
          <MetricBox
            label="Peak Views"
            value={
              summary.popular_pages && summary.popular_pages.length > 0
                ? summary.popular_pages[0].views
                : 0
            }
          />
        </div>
      </div>

      {/* Recommendations */}
      {summary.popular_pages && summary.popular_pages.length > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="flex gap-3">
            <div className="text-blue-600 mt-0.5">
              <TrendingUp size={20} />
            </div>
            <div>
              <h4 className="font-semibold text-blue-900">Insights</h4>
              <p className="text-sm text-blue-800 mt-1">
                Page {summary.popular_pages[0].page} is your most viewed page with{' '}
                {summary.popular_pages[0].views} views. Consider adding more interactive hotspots
                there to increase engagement.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function KPICard({ title, value, icon, color }) {
  const colorClasses = {
    blue: 'bg-blue-50 text-blue-600',
    purple: 'bg-purple-50 text-purple-600',
    green: 'bg-green-50 text-green-600',
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-6">
      <div className={`w-12 h-12 rounded-lg ${colorClasses[color]} flex items-center justify-center mb-3`}>
        {icon}
      </div>
      <p className="text-sm font-medium text-gray-600 mb-1">{title}</p>
      <p className="text-3xl font-bold text-gray-900">{value}</p>
    </div>
  );
}

function MetricBox({ label, value }) {
  return (
    <div className="bg-gray-50 rounded-lg p-4 text-center">
      <p className="text-xs font-medium text-gray-600 mb-2">{label}</p>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
    </div>
  );
}
