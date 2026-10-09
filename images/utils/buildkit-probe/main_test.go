package main

import (
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRejectsUnspecifiedOrRemoteTarget(t *testing.T) {
	for _, args := range [][]string{
		{},
		{"--host", "tcp://localhost:2375", "--expected-daemon-id", "fixture"},
		{"--host", "unix://relative", "--expected-daemon-id", "fixture"},
		{"--host", "unix:///missing", "--builder", "other"},
	} {
		if err := run(args, io.Discard); err == nil {
			t.Errorf("unsafe target accepted: %v", args)
		}
	}
}

func TestDaemonMismatchPrecedesBuildkitSession(t *testing.T) {
	root, err := os.MkdirTemp("/tmp", "ci-buildkit-probe-")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.RemoveAll(root) })
	socket := filepath.Join(root, "docker.sock")
	listener, err := net.Listen("unix", socket)
	if err != nil {
		t.Fatal(err)
	}
	server := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.URL.Path == "/_ping":
			w.Header().Set("API-Version", "1.54")
			_, _ = io.WriteString(w, "OK")
		case strings.HasSuffix(r.URL.Path, "/info"):
			_, _ = io.WriteString(w, `{"ID":"other-daemon","OSType":"linux"}`)
		default:
			t.Errorf("unexpected request before identity verification: %s %s", r.Method, r.URL.Path)
			w.WriteHeader(http.StatusBadRequest)
		}
	})}
	go func() { _ = server.Serve(listener) }()
	t.Cleanup(func() { _ = server.Close() })
	err = run([]string{"--host", "unix://" + socket, "--expected-daemon-id", "expected-daemon"}, io.Discard)
	if err == nil || !strings.Contains(err.Error(), "identity mismatch") {
		t.Fatalf("wanted daemon identity mismatch, got %v", err)
	}
}
