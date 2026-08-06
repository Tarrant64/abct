#!/usr/bin/env ruby
# frozen_string_literal: true

require 'xcodeproj'
require 'set'

PROJECT_PATH = File.expand_path('../ios/Runner.xcodeproj', __dir__)
APP_GROUP = 'group.com.teamcata.abct'
RUNNER_ENTITLEMENTS = 'Runner/Runner.entitlements'
WATCH_ENTITLEMENTS = 'watchos_companion/WatchApp/WatchApp.entitlements'
WIDGET_ENTITLEMENTS = 'watchos_companion/WidgetExtension/WidgetExtension.entitlements'

WATCH_SWIFT_FILES = [
  'watchos_companion/WatchApp/PortfolioWatchApp.swift',
  'watchos_companion/WatchApp/PortfolioWatchView.swift',
  'watchos_companion/WatchApp/SparklineShape.swift',
  'watchos_companion/WatchApp/PortfolioWatchModel.swift',
  'watchos_companion/WatchApp/SharedPortfolioSnapshotStore.swift',
  'watchos_companion/WatchApp/WatchHandoffController.swift'
].freeze

WIDGET_SWIFT_FILES = [
  'watchos_companion/WidgetExtension/PortfolioComplicationWidget.swift'
].freeze

def ensure_file_ref(project, relative_path)
  base = File.basename(relative_path)
  existing = project.files.find do |f|
    f.path == relative_path || f.path == base
  end
  return existing if existing

  root = project.main_group['watchos_companion'] || project.main_group.new_group('watchos_companion', 'watchos_companion')

  group = root
  path_parts = relative_path.sub('watchos_companion/', '').split('/')
  path_parts[0..-2].each do |part|
    found = group.children.find { |c| c.respond_to?(:display_name) && c.display_name == part }
    group = found || group.new_group(part, part)
  end

  group.new_file(base)
end

def ensure_sources(target, file_refs)
  source_phase = target.source_build_phase
  existing_paths = source_phase.files_references.map(&:path).compact.to_set
  file_refs.each do |ref|
    next if existing_paths.include?(ref.path)

    source_phase.add_file_reference(ref, true)
  end
end

def apply_entitlements(target, path)
  target.build_configurations.each do |config|
    config.build_settings['CODE_SIGN_ENTITLEMENTS'] = path
  end
end

def detect_watch_target(project)
  project.targets.find do |t|
    type = t.product_type.to_s
    name = t.name.downcase
    (type.include?('watchapp') || type.include?('watch') || name.include?('watch app')) &&
      !name.include?('widget')
  end
end

def detect_widget_target(project)
  project.targets.find do |t|
    type = t.product_type.to_s
    name = t.name.downcase
    type.include?('app-extension') && name.include?('widget')
  end
end

project = Xcodeproj::Project.open(PROJECT_PATH)
runner = project.targets.find { |t| t.name == 'Runner' }
watch_target = detect_watch_target(project)
widget_target = detect_widget_target(project)

unless runner
  abort('Runner target not found.')
end

apply_entitlements(runner, RUNNER_ENTITLEMENTS)

if watch_target.nil? || widget_target.nil?
  puts 'Watch and/or Widget targets not found yet.'
  puts 'Create them in Xcode first, then rerun:'
  puts '  ruby scripts/configure_watch_companion.rb'
  project.save
  exit 2
end

watch_refs = WATCH_SWIFT_FILES.map { |path| ensure_file_ref(project, path) }
widget_refs = WIDGET_SWIFT_FILES.map { |path| ensure_file_ref(project, path) }

ensure_sources(watch_target, watch_refs)
ensure_sources(widget_target, widget_refs)

apply_entitlements(watch_target, WATCH_ENTITLEMENTS)
apply_entitlements(widget_target, WIDGET_ENTITLEMENTS)

project.save

puts 'Configured watch companion successfully:'
puts "- Runner entitlements: #{RUNNER_ENTITLEMENTS}"
puts "- Watch target: #{watch_target.name}"
puts "- Widget target: #{widget_target.name}"
puts "- App Group: #{APP_GROUP}"
