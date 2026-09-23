# Advanced: automations and webhooks

Everything on this page is **optional**. Since v2 the integration handles the
common bird notifications itself — configure them under **Settings >
Devices & Services > BirdNET-Go > Configure**:

- *Notify on new detections* (with a cooldown and a **Reset** button on the
  notification)
- *Notify when a species is heard for the first time*
- *Notify when a species returns after a long absence*

The examples below cover cases the built-ins deliberately don't, such as
low-latency webhook notifications pushed by BirdNET-Go itself, per-camera
friendly names, and confidence values in the message.

## Webhook notifications with per-detection detail

The analytics API doesn't know which camera detected a bird or the detection
confidence. If you want those in your notifications, have BirdNET-Go call a
Home Assistant webhook through a custom action.

You will need:

1. A **timer** helper (e.g. 15 minutes) for the notification cooldown
2. A **text** helper to display the last notification
3. The BirdNET-Go side: [`scripts/birdnet_notify_ha.sh`](../scripts/birdnet_notify_ha.sh)
   added as a custom action under BirdNET-Go **Settings > Species** (include
   the `CommonName`, `Confidence`, `Time`, and `Source` parameters), pointed at
   your webhook URL. Restart BirdNET-Go after changing species settings.

Update the `webhook_id`, timer, text, and notify entity IDs before pasting.

### Notify bird detection

```yaml
alias: Notify Bird Detection
description: >-
  Sends a notification when the bird detection script calls the webhook,
  handling success and error cases.
triggers:
  - trigger: webhook
    allowed_methods:
      - POST
      - PUT
    local_only: true
    webhook_id: notify-bird-detection-123456789
conditions: []
actions:
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ trigger.json.type == 'bird_detection' }}"
            alias: Bird Detection
          - condition: not
            conditions:
              - condition: state
                entity_id: timer.bird_notification_cooldown
                state: active
        sequence:
          - parallel:
              - data:
                  title: "🦜 {{ trigger.json.common_name }} Detected!"
                  message: |
                    Time: {{ trigger.json.time }}
                    Camera: {{ trigger.json.source_camera }}
                    Confidence: {{ trigger.json.confidence_pct }}
                  data:
                    notification_icon: mdi:bird
                    group: birdnet-alert
                    channel: birdnet-alert
                    tag: birdnet-alert
                    ttl: 0
                    priority: high
                    push:
                      interruption-level: time-sensitive
                      sound: bert.wav
                    actions:
                      - action: BIRD_NOTIFICATION_COOLDOWN_RESET
                        title: Reset
                action: notify.family
              - action: timer.start
                metadata: {}
                data: {}
                target:
                  entity_id: timer.bird_notification_cooldown
              - action: input_text.set_value
                metadata: {}
                data:
                  value: >-
                    {{ trigger.json.time }}: {{ trigger.json.common_name }}, {{
                    trigger.json.source_camera }}, {{
                    trigger.json.confidence_pct }}
                target:
                  entity_id: input_text.last_bird_notification
      - conditions:
          - condition: template
            value_template: "{{ trigger.json.type == 'script_error' }}"
            alias: Script Error
        sequence:
          - data:
              message: >-
                Received unexpected payload type from bird script webhook: {{
                trigger.json | tojson }}
              level: warning
            action: system_log.write
          - data:
              title: Bird Script Error Reported
              message: >
                Reason: {{ trigger.json.reason }}

                Missing Args: {{ trigger.json.missing_args | default('None
                specified') }}
              data:
                notification_icon: mdi:bird
                group: birdnet-alert
                channel: birdnet-alert
                tag: birdnet-alert
                ttl: 0
                priority: high
                push:
                  interruption-level: time-sensitive
            action: notify.family
mode: single
```

### Reset the cooldown from the notification

```yaml
alias: Bird Notification Cooldown Timer Reset
description: >-
  Resets the Bird Notification Cooldown Timer so another bird notification
  can come through.
triggers:
  - event_type: mobile_app_notification_action
    event_data:
      action: BIRD_NOTIFICATION_COOLDOWN_RESET
    trigger: event
conditions: []
actions:
  - action: timer.cancel
    metadata: {}
    data: {}
    target:
      entity_id:
        - timer.bird_notification_cooldown
mode: single
```

> Recent BirdNET-Go snapshots added native notification channels and webhooks
> which may cover these use cases without custom scripts. Check your
> BirdNET-Go version first.

## Faster refresh via MQTT

With the integration, sensors update on their own scan interval. If you run
BirdNET-Go with MQTT configured against the same broker as Home Assistant,
you can cut detection latency by forcing a refresh whenever BirdNET-Go
publishes a new detection.

1. Configure the MQTT integration in BirdNET-Go and publish to the same
   broker Home Assistant uses.
2. Add the template sensor below to your `template.yaml` (referenced from
   `configuration.yaml` as `template: !include template.yaml`).
3. Add the automation below; it forces the BirdNET-Go sensors to refresh
   whenever BirdNET-Go publishes over MQTT.

```yaml
# --- template.yaml ---
- trigger:
    - platform: mqtt
      topic: birdnet
    # Reset at midnight to align with "a new daily summary"
    - platform: time_pattern
      hours: 0
      minutes: 0
      id: reset
  sensor:
    - name: BirdNET
      unique_id: birdnet
      state: >-
        {% if trigger.id == 'reset' %}
          unavailable
        {% elif trigger.payload_json is defined %}
          {{ today_at(trigger.payload_json.Time) }}
        {% else %}
          unknown
        {% endif %}
      icon: mdi:bird
```

```yaml
# --- automations.yaml ---
alias: Trigger BirdNET-Go API fetch
triggers:
  - trigger: state
    entity_id:
      - sensor.birdnet
conditions: []
actions:
  - parallel:
      - action: homeassistant.update_entity
        metadata: {}
        data:
          entity_id:
            - sensor.birdnet_daily_summary
      - action: homeassistant.update_entity
        metadata: {}
        data:
          entity_id:
            - sensor.birdnet_species_summary
mode: queued
max: 5
```
