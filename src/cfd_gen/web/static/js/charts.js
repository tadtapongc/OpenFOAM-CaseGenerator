/**
 * Convergence and Residuals Charts using Chart.js
 */

class TelemetryCharts {
  constructor() {
    this.forcesChart = null;
    this.residualsChart = null;
    this.initForcesChart();
    this.initResidualsChart();
  }

  initForcesChart() {
    const ctx = document.getElementById('chart-forces');
    if (!ctx || typeof Chart === 'undefined') return;

    this.forcesChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          {
            label: 'Downforce (-Fy) [N]',
            data: [],
            borderColor: '#00d2ff',
            backgroundColor: 'rgba(0, 210, 255, 0.1)',
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 4,
            tension: 0.1,
            yAxisID: 'y',
          },
          {
            label: 'Drag (-Fz) [N]',
            data: [],
            borderColor: '#f43f5e',
            backgroundColor: 'rgba(244, 63, 94, 0.1)',
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 4,
            tension: 0.1,
            yAxisID: 'y1',
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: {
          mode: 'index',
          intersect: false,
        },
        plugins: {
          legend: {
            labels: {
              color: '#94a3b8',
              font: { family: 'Inter', size: 11 },
            },
          },
          tooltip: {
            backgroundColor: '#1a2234',
            titleColor: '#00d2ff',
            bodyColor: '#f1f5f9',
            borderColor: '#1f2a3f',
            borderWidth: 1,
          },
        },
        scales: {
          x: {
            title: { display: true, text: 'Iteration', color: '#64748b' },
            ticks: { color: '#64748b', maxTicksLimit: 8 },
            grid: { color: '#1f2a3f' },
          },
          y: {
            type: 'linear',
            display: true,
            position: 'left',
            title: { display: true, text: 'Downforce (N)', color: '#00d2ff' },
            ticks: { color: '#00d2ff' },
            grid: { color: '#1f2a3f' },
          },
          y1: {
            type: 'linear',
            display: true,
            position: 'right',
            title: { display: true, text: 'Drag (N)', color: '#f43f5e' },
            ticks: { color: '#f43f5e' },
            grid: { drawOnChartArea: false },
          },
        },
      },
    });
  }

  initResidualsChart() {
    const ctx = document.getElementById('chart-residuals');
    if (!ctx || typeof Chart === 'undefined') return;

    this.residualsChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'p', data: [], borderColor: '#38bdf8', borderWidth: 1.5, pointRadius: 0 },
          { label: 'Ux', data: [], borderColor: '#a855f7', borderWidth: 1.5, pointRadius: 0 },
          { label: 'Uy', data: [], borderColor: '#10b981', borderWidth: 1.5, pointRadius: 0 },
          { label: 'Uz', data: [], borderColor: '#f59e0b', borderWidth: 1.5, pointRadius: 0 },
          { label: 'k', data: [], borderColor: '#ec4899', borderWidth: 1.5, pointRadius: 0 },
          { label: 'omega', data: [], borderColor: '#6366f1', borderWidth: 1.5, pointRadius: 0 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: {
            labels: {
              color: '#94a3b8',
              font: { family: 'Inter', size: 10 },
              boxWidth: 12,
            },
          },
        },
        scales: {
          x: {
            ticks: { color: '#64748b', maxTicksLimit: 8 },
            grid: { color: '#1f2a3f' },
          },
          y: {
            type: 'logarithmic',
            title: { display: true, text: 'Initial Residual', color: '#64748b' },
            ticks: { color: '#64748b' },
            grid: { color: '#1f2a3f' },
          },
        },
      },
    });
  }

  updateForces(series) {
    if (!this.forcesChart || !series) return;
    this.forcesChart.data.labels = series.iterations;
    this.forcesChart.data.datasets[0].data = series.downforce;
    this.forcesChart.data.datasets[1].data = series.drag;
    this.forcesChart.update('none');
  }

  updateResiduals(iterations, residualsMap) {
    if (!this.residualsChart || !residualsMap) return;
    this.residualsChart.data.labels = iterations;
    
    const varNames = ['p', 'Ux', 'Uy', 'Uz', 'k', 'omega'];
    this.residualsChart.data.datasets.forEach((ds) => {
      if (residualsMap[ds.label]) {
        ds.data = residualsMap[ds.label];
      }
    });
    this.residualsChart.update('none');
  }
}

window.TelemetryCharts = TelemetryCharts;
