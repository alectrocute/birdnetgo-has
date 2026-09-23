# Advanced: custom dashboards

The integration creates a **Birds** dashboard in your sidebar automatically
(see the [README](../README.md)), and it is a normal Home Assistant dashboard —
you can edit, rearrange, or delete its cards in the UI. If you break it, run
**Configure** on the BirdNET-Go integration and enable *Reset the Birds
dashboard to the default layout*.

The examples below are **optional** community favorites that go beyond the
built-in dashboard. Nothing here is required.

## Button-card dashboards

Polished, sortable tables with species photos served straight from your
BirdNET-Go instance. Requires the
[button-card](https://github.com/custom-cards/button-card) plugin
(HACS > Frontend > button-card).

Add a **Manual** card on any dashboard and paste one of the configs below.

The thumbnail URL resolves in this order:

1. The card's `birdnet_frontend_url` variable (per-card override)
2. The integration's **Frontend URL** option
3. The integration's BirdNET-Go base URL

If no URL is available (or a photo 404s), a 🐦 placeholder is shown instead.

### Latest detections with photos

```yaml
type: custom:button-card
entity: sensor.birdnet_species_summary
triggers_update:
  - sensor.birdnet_species_summary
variables:
  birdnet_frontend_url: ""
show_icon: false
show_name: false
show_state: false
grid_options:
  columns: 12
styles:
  card:
    - padding: 16px
    - height: 100%
  custom_fields:
    content:
      - width: 100%
      - display: block !important
      - justify-self: stretch !important
      - align-self: stretch !important
custom_fields:
  content: |
    [[[
      const speciesData = states['sensor.birdnet_species_summary']?.attributes?.species_list;
      if (!speciesData || speciesData.length === 0) {
        return '<p style="color:var(--secondary-text-color);">No recent bird data available.</p>';
      }

      const attrs = states['sensor.birdnet_species_summary']?.attributes || {};
      const baseUrl = (variables.birdnet_frontend_url || attrs.frontend_url || attrs.base_url || '').replace(/\/+$/, '');

      const sorted = [...speciesData].sort((a, b) => {
        const aTime = a.last_heard || '1970-01-01 00:00:00';
        const bTime = b.last_heard || '1970-01-01 00:00:00';
        return bTime.localeCompare(aTime);
      }).slice(0, 11);

      function getRelativeTime(dateString) {
        const date = new Date(dateString.replace(' ', 'T'));
        const now = new Date();
        const diffInSeconds = Math.floor((now - date) / 1000);
        if (isNaN(diffInSeconds) || diffInSeconds < 0) return 'Just now';
        if (diffInSeconds < 60) return `${diffInSeconds}s`;
        const diffInMinutes = Math.floor(diffInSeconds / 60);
        if (diffInMinutes < 60) return `${diffInMinutes}m`;
        const diffInHours = Math.floor(diffInMinutes / 60);
        if (diffInHours < 24) return `${diffInHours}h`;
        const diffInDays = Math.floor(diffInHours / 24);
        return `${diffInDays}d`;
      }

      let tableHtml = `
        <style>
          #container:has(.bird-table) { display: flex; }
          .bird-table { width: 100%; font-size: 0.9em; border-collapse: collapse; }
          .bird-table th { text-align: center; padding: 8px 4px; border-bottom: 1px solid var(--divider-color); color: var(--secondary-text-color); font-weight: 500; }
          .bird-table td { padding: 8px 4px; border-bottom: 1px solid var(--divider-color); }
          .bird-table tr:last-child td { border-bottom: none; }
          .bird-table tr:hover { background-color: var(--table-row-alternative-background-color); }
          .bird-table img { border-radius: 6px; object-fit: cover; display: block; margin: 0 auto; }
          .bird-table a { color: var(--primary-color); text-decoration: none; font-weight: 500; }
          .bird-table a:hover { text-decoration: underline; }
          .bird-table .time-col { color: var(--secondary-text-color); white-space: nowrap; }
        </style>
        <div style="width: 100%; display: block;">
          <table class="bird-table">
            <thead>
              <tr>
                <th style="text-align:center;">Photo</th>
                <th>Species</th>
                <th>Last Heard</th>
              </tr>
            </thead>
            <tbody>
      `;

      for (const bird of sorted) {
        const time = bird.last_heard || '1970-01-01 00:00:00';
        const name = bird.common_name || 'Unknown';
        const scientificName = bird.scientific_name || '';
        const speciesCode = bird.species_code || '';
        const ebirdUrl = speciesCode ? `https://ebird.org/species/${speciesCode}` : '#';
        const timeAgo = getRelativeTime(time);

        const nameLink = (speciesCode.length >= 1 && speciesCode.length <= 7)
          ? `<a href="${ebirdUrl}" target="_blank">${name}</a>`
          : name;

        const imageUrl = baseUrl
          ? `${baseUrl}/api/v2/media/image/${encodeURIComponent(scientificName)}`
          : '';
        const photo = imageUrl
          ? `<img src="${imageUrl}" width="48" height="48" alt="${name}" onerror="this.outerHTML='<span style=&quot;font-size:32px;line-height:48px;&quot;>🐦</span>'"/>`
          : '<span style="font-size:32px;line-height:48px;">🐦</span>';

        tableHtml += `<tr>
          <td style="text-align:center; width: 60px;">${photo}</td>
          <td>${nameLink}</td>
          <td class="time-col">${timeAgo} ago</td>
        </tr>`;
      }
      tableHtml += '</tbody></table></div>';
      return tableHtml;
    ]]]
```

### Daily summary with activity sparklines

```yaml
type: custom:button-card
entity: sensor.birdnet_daily_summary
triggers_update:
  - sensor.birdnet_daily_summary
show_icon: false
show_name: false
show_state: false
grid_options:
  columns: 12
styles:
  card:
    - padding: 16px
    - background: var(--ha-card-background)
    - height: 100%
    - width: auto
  custom_fields:
    content:
      - width: 100%
custom_fields:
  content: |
    [[[
      const speciesData = states['sensor.birdnet_daily_summary']?.attributes?.species_list;
      if (!speciesData || speciesData.length === 0) {
        return '<p style="color:var(--secondary-text-color);">No bird species data available or list is empty.</p>';
      }

      const sorted = [...speciesData].sort((a, b) => {
        const aTime = a.latest_heard || '00:00:00';
        const bTime = b.latest_heard || '00:00:00';
        if (bTime !== aTime) return bTime.localeCompare(aTime);
        return (b.count || 0) - (a.count || 0);
      });

      let tableHtml = `
        <style>
          .daily-table { width: 100%; border-collapse: collapse; font-size: 0.85em; }
          .daily-table th { text-align: left; padding: 8px 4px; border-bottom: 1px solid var(--divider-color); color: var(--secondary-text-color); font-weight: 500; }
          .daily-table td { padding: 8px 4px; border-bottom: 1px solid var(--divider-color); }
          .daily-table tr:last-child td { border-bottom: none; }
          .daily-table tr:nth-child(even) { background-color: var(--table-row-alternative-background-color); }
          .daily-table tr:hover { background-color: var(--secondary-background-color); }
          .daily-table .time-col { color: var(--secondary-text-color); white-space: nowrap; }
          .daily-table .count-col { text-align: right; font-weight: 500; }
          .daily-table .sparkline-col { text-align: center; font-family: monospace; letter-spacing: 1px; font-size: 1.1em; color: var(--primary-color); }
          .daily-table a { color: var(--primary-color); text-decoration: none; }
          .daily-table a:hover { text-decoration: underline; }
          .summary-footer { margin-top: 12px; font-size: 0.85em; color: var(--secondary-text-color); text-align: right; }
        </style>
        <table class="daily-table">
          <thead>
            <tr>
              <th>Last Heard</th>
              <th>Species</th>
              <th style="text-align:right;">Count</th>
              <th style="text-align:center;">Sparkline (6AM–6PM)</th>
            </tr>
          </thead>
          <tbody>
      `;

      for (const bird of sorted) {
        const time = bird.latest_heard || '00:00:00';
        const name = bird.common_name || 'Unknown';
        const count = bird.count || 0;
        const speciesCode = bird.species_code || '';
        const ebirdUrl = speciesCode ? `https://ebird.org/species/${speciesCode}` : '#';

        let sparkline = 'N/A';
        const hourly = bird.hourly_counts;
        if (Array.isArray(hourly) && hourly.length === 24) {
          const earlySum = hourly.slice(0, 6).reduce((a, b) => a + b, 0);
          const middlePart = hourly.slice(6, 18);
          const lateSum = hourly.slice(18, 24).reduce((a, b) => a + b, 0);
          const aggregated = [earlySum, ...middlePart, lateSum];

          if (aggregated.length === 14) {
            const maxVal = Math.max(...aggregated);
            const sparkChars = ['▁', '▂', '▃', '▄', '▅', '▆', '▇'];
            sparkline = aggregated.map(v => {
              if (maxVal === 0) return sparkChars[0];
              const idx = Math.min(6, Math.floor(v * 7 / maxVal));
              return sparkChars[idx];
            }).join('');
          }
        }

        const nameLink = (speciesCode.length >= 1 && speciesCode.length <= 7)
          ? `<a href="${ebirdUrl}" target="_blank">${name}</a>`
          : name;

        const displayTime = time.substring(0, 5);

        tableHtml += `<tr>
          <td class="time-col">${displayTime}</td>
          <td>${nameLink}</td>
          <td class="count-col">${count}</td>
          <td class="sparkline-col">${sparkline}</td>
        </tr>`;
      }
      tableHtml += '</tbody></table>';

      const totalDetections = speciesData.reduce((sum, b) => sum + (b.count || 0), 0);
      tableHtml += `<div class="summary-footer">
        ${totalDetections} Detections · ${speciesData.length} Species
      </div>`;
      return tableHtml;
    ]]]
```

## Notes

- The markdown cards on the built-in dashboard read the live sensors, so they
  reflect real-time state (even when BirdNET-Go is down).
- The `species_list` attributes can get large. You may want to exclude the
  BirdNET-Go sensors from the recorder (see the
  [README](../README.md#recommended-exclude-sensors-from-the-recorder)).
