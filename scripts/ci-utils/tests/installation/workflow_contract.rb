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
