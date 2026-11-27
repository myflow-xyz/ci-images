package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"io"
	"net"
	"os"
	"runtime/debug"
	"strings"
	"time"

	"github.com/moby/buildkit/client"
	gateway "github.com/moby/buildkit/frontend/gateway/client"
	"github.com/moby/buildkit/solver/pb"
	dockerclient "github.com/moby/moby/client"
)

type capabilityReport struct {
	DaemonID        string `json:"daemon_id"`
	Builder         string `json:"builder"`
	Driver          string `json:"driver"`
	WorkerID        string `json:"worker_id"`
	BuildkitVersion string `json:"buildkit_version"`
	BuildkitModule  string `json:"buildkit_module_version"`
	GCSpaceFilters  bool   `json:"gc_space_filters"`
}

func run(args []string, output io.Writer) error {
	flags := flag.NewFlagSet("ci-buildkit-probe", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	host := flags.String("host", "", "explicit local Docker Unix endpoint")
	expected := flags.String("expected-daemon-id", "", "required daemon identity")
	timeout := flags.Duration("timeout", 30*time.Second, "bounded probe deadline")
	if err := flags.Parse(args); err != nil {
		return errors.New("invalid capability probe arguments")
	}
	if flags.NArg() != 0 || !strings.HasPrefix(*host, "unix:///") || *host == "unix:///" ||
		strings.ContainsAny(*host, "\x00\r\n?#") || *expected == "" || *timeout <= 0 || *timeout > 15*time.Minute {
		return errors.New("an explicit local Unix endpoint, daemon identity, and bounded timeout are required")
	}
	ctx, cancel := context.WithTimeout(context.Background(), *timeout)
	defer cancel()
	// No FromEnv or context store: this probe can only reach the supplied daemon.
	engine, err := dockerclient.New(dockerclient.WithHost(*host), dockerclient.WithAPIVersionNegotiation())
	if err != nil {
		return errors.New("cannot initialize the selected Docker client")
	}
	defer engine.Close()
	info, err := engine.Info(ctx, dockerclient.InfoOptions{})
	if err != nil {
		return errors.New("cannot inspect the selected Docker daemon")
	}
	if info.Info.ID != *expected {
		return errors.New("daemon identity mismatch")
	}
	if info.Info.OSType != "linux" {
		return errors.New("only Linux Docker is supported")
	}
	for _, option := range info.Info.SecurityOptions {
		if strings.Contains(option, "rootless") || strings.Contains(option, "userns") {
			return errors.New("rootless and user-namespace deployments need separate qualification")
		}
	}
	// Use the local docker driver's existing transports, without builder stores
	// or lifecycle operations. These are the same endpoints used by Buildx.
	bk, err := client.New(ctx, "",
		client.WithContextDialer(func(dialContext context.Context, _ string) (net.Conn, error) {
			return engine.DialHijack(dialContext, "/grpc", "h2c", nil)
		}),
		client.WithSessionDialer(func(dialContext context.Context, protocol string, metadata map[string][]string) (net.Conn, error) {
			return engine.DialHijack(dialContext, "/session", protocol, metadata)
		}))
	if err != nil {
		return errors.New("cannot connect to the local default BuildKit backend")
	}
	defer bk.Close()
	bkInfo, err := bk.Info(ctx)
	if err != nil {
		return errors.New("cannot inspect the local BuildKit version")
	}
	workers, err := bk.ListWorkers(ctx)
	if err != nil || len(workers) != 1 {
		return errors.New("exactly one local Docker BuildKit worker is required")
	}
	report := capabilityReport{
		DaemonID: info.Info.ID, Builder: "default", Driver: "docker", WorkerID: workers[0].ID,
		BuildkitVersion: bkInfo.BuildkitVersion.Version, BuildkitModule: "unknown",
	}
	if build, ok := debug.ReadBuildInfo(); ok {
		for _, dependency := range build.Deps {
			if dependency.Path == "github.com/moby/buildkit" {
				report.BuildkitModule = dependency.Version
			}
		}
	}
	// Match Buildx's capability handshake: an internal session whose callback only
	// reads advertised capabilities. It submits no workload definition, frontend
	// image, exporter, or prune request; BuildKit may record internal session metadata.
	_, err = bk.Build(ctx, client.SolveOpt{Internal: true}, "ci-utils-capabilities",
		func(_ context.Context, gatewayClient gateway.Client) (*gateway.Result, error) {
			capabilities := gatewayClient.BuildOpts().LLBCaps
			report.GCSpaceFilters = capabilities.Supports(pb.CapGCFreeSpaceFilter) == nil
			return nil, nil
		}, nil)
	if err != nil {
		return errors.New("cannot read the backend cache-space capability")
	}
	return json.NewEncoder(output).Encode(report)
}

func main() {
	if err := run(os.Args[1:], os.Stdout); err != nil {
		_ = json.NewEncoder(os.Stderr).Encode(map[string]string{"error": err.Error()})
		os.Exit(2)
	}
}
