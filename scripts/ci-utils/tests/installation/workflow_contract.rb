# Verify the permissions of the jobs that execute pull-request code.
require "yaml"

workflows = File.expand_path("../../../../.github/workflows", __dir__)
helpers = YAML.load_file(File.join(workflows, "runner-helper.yml"))
helpers.fetch("jobs").each_value do |job|
  permissions = job.fetch("permissions", helpers.fetch("permissions"))
  abort "PR qualification requires only contents: read" unless permissions == {"contents" => "read"}
  job.fetch("steps").each do |step|
    abort "PR qualification must not log in to a registry" if step["uses"].to_s.start_with?("docker/login-action@")
    if step["uses"].to_s.start_with?("actions/checkout@")
      abort "PR checkout retained credentials" unless step.dig("with", "persist-credentials") == false
    end
  end
end

# Publication depends on the native jobs at the dispatched commit. GitHub resolves
# a local reusable workflow and the default checkout against the caller's SHA.
jobs = YAML.load_file(File.join(workflows, "release.yml")).fetch("jobs")
release = jobs.fetch("release")
gate = Array(release["needs"]).map { |id| jobs.fetch(id) }.find do |job|
  job["uses"] == "./.github/workflows/runner-helper.yml"
end
abort "publication requires native qualification" unless gate && !gate["if"] && !release["if"]
linux = helpers.fetch("jobs").fetch("native")
platforms = linux.dig("strategy", "matrix", "include").map { |j| j.fetch("platform") }
abort "both Linux architectures must qualify" unless platforms.sort == %w[linux/amd64 linux/arm64]
[linux, helpers.fetch("jobs").fetch("macos-client")].each do |job|
  abort "native qualification must succeed" if job["if"] || job["continue-on-error"]
  checkout = job.fetch("steps").find { |step| step["uses"].to_s.start_with?("actions/checkout@") }
  abort "native qualification must check out the release commit" unless checkout && [nil, '${{ github.sha }}'].include?(checkout.dig("with", "ref"))
end
