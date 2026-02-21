import { useState, useEffect } from "react";
import "@/App.css";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function App() {
  const [step, setStep] = useState(1);
  const [generating, setGenerating] = useState(false);
  const [generatorInfo, setGeneratorInfo] = useState(null);
  
  // Form state
  const [config, setConfig] = useState({
    metadata: {
      name: "my-service",
      version: "1.0.0",
      description: "Production-grade microservice",
      author: "Your Team",
      port: 8000,
      api_prefix: "/api/v1"
    },
    language: "python_fastapi",
    database: {
      database_type: "postgresql",
      enable_migrations: true,
      enable_backup_scripts: true,
      enable_integrity_checks: true,
      connection_pool_size: 20,
      connection_timeout: 30
    },
    security: {
      auth_type: "api_key",
      enable_rbac: true,
      rate_limit_per_minute: 100,
      rate_limit_burst: 200,
      enable_cors: true,
      cors_origins: ["*"],
      jwt_expiry_hours: 24,
      api_key_header: "X-API-Key"
    },
    observability: {
      enable_prometheus: true,
      enable_structured_logging: true,
      enable_tracing: true,
      log_level: "INFO",
      metrics_port: 9090
    },
    cicd: {
      platform: "github_actions",
      enable_sbom: true,
      enable_signing: true,
      enable_security_scan: true,
      coverage_threshold: 85,
      enable_fuzz_testing: true,
      environments: ["dev", "staging", "production"]
    },
    kubernetes: {
      enable_hpa: true,
      enable_pdb: true,
      enable_network_policy: true,
      enable_service_monitor: true,
      min_replicas: 2,
      max_replicas: 10,
      target_cpu_utilization: 70,
      resource_requests_cpu: "100m",
      resource_requests_memory: "128Mi",
      resource_limits_cpu: "500m",
      resource_limits_memory: "512Mi"
    },
    deployment_target: "both",
    enable_helm: false,
    enable_api_docs: true,
    enable_health_checks: true,
    enable_graceful_shutdown: true
  });

  useEffect(() => {
    fetchGeneratorInfo();
  }, []);

  const fetchGeneratorInfo = async () => {
    try {
      const response = await axios.get(`${API}/generator/info`);
      setGeneratorInfo(response.data);
    } catch (error) {
      console.error("Failed to fetch generator info:", error);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const response = await axios.post(`${API}/generate`, config, {
        responseType: 'blob'
      });

      // Download the ZIP file
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `${config.metadata.name}.zip`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      
      alert('✅ Microservice generated successfully!');
    } catch (error) {
      console.error("Generation failed:", error);
      alert('❌ Generation failed: ' + (error.response?.data?.detail || error.message));
    } finally {
      setGenerating(false);
    }
  };

  const updateConfig = (path, value) => {
    setConfig(prev => {
      const newConfig = { ...prev };
      const keys = path.split('.');
      let current = newConfig;
      
      for (let i = 0; i < keys.length - 1; i++) {
        current = current[keys[i]];
      }
      
      current[keys[keys.length - 1]] = value;
      return newConfig;
    });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-blue-900 to-gray-900">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-5xl font-bold text-white mb-4">
            🚀 Maximal Microservice Generator
          </h1>
          <p className="text-xl text-gray-300">
            Generate production-ready microservices with complete CI/CD, observability, and security
          </p>
        </div>

        {/* Generator Info */}
        {generatorInfo && (
          <div className="bg-white/10 backdrop-blur-lg rounded-lg p-6 mb-8 border border-white/20">
            <h2 className="text-2xl font-bold text-white mb-4">✨ Features</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {generatorInfo.features.slice(0, 9).map((feature, idx) => (
                <div key={idx} className="flex items-start space-x-2">
                  <span className="text-green-400 text-xl">✓</span>
                  <span className="text-gray-200 text-sm">{feature}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Configuration Form */}
        <div className="bg-white/10 backdrop-blur-lg rounded-lg p-8 border border-white/20">
          {/* Step Indicators */}
          <div className="flex justify-center mb-8 space-x-4">
            {[1, 2, 3, 4].map(s => (
              <button
                key={s}
                onClick={() => setStep(s)}
                className={`w-12 h-12 rounded-full font-bold transition-all ${
                  step === s
                    ? 'bg-blue-500 text-white scale-110'
                    : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                }`}
              >
                {s}
              </button>
            ))}
          </div>

          {/* Step 1: Basic Info */}
          {step === 1 && (
            <div className="space-y-6">
              <h2 className="text-2xl font-bold text-white mb-6">📝 Service Metadata</h2>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Service Name *
                  </label>
                  <input
                    type="text"
                    value={config.metadata.name}
                    onChange={(e) => updateConfig('metadata.name', e.target.value)}
                    className="w-full px-4 py-2 bg-white/20 border border-white/30 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="my-service"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Version
                  </label>
                  <input
                    type="text"
                    value={config.metadata.version}
                    onChange={(e) => updateConfig('metadata.version', e.target.value)}
                    className="w-full px-4 py-2 bg-white/20 border border-white/30 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Description *
                  </label>
                  <textarea
                    value={config.metadata.description}
                    onChange={(e) => updateConfig('metadata.description', e.target.value)}
                    className="w-full px-4 py-2 bg-white/20 border border-white/30 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    rows="3"
                    placeholder="Production-grade microservice"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Author
                  </label>
                  <input
                    type="text"
                    value={config.metadata.author}
                    onChange={(e) => updateConfig('metadata.author', e.target.value)}
                    className="w-full px-4 py-2 bg-white/20 border border-white/30 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Port
                  </label>
                  <input
                    type="number"
                    value={config.metadata.port}
                    onChange={(e) => updateConfig('metadata.port', parseInt(e.target.value))}
                    className="w-full px-4 py-2 bg-white/20 border border-white/30 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>

              <button
                onClick={() => setStep(2)}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-6 rounded-lg transition-colors"
              >
                Next: Database & Security →
              </button>
            </div>
          )}

          {/* Step 2: Database & Security */}
          {step === 2 && (
            <div className="space-y-6">
              <h2 className="text-2xl font-bold text-white mb-6">🔒 Database & Security</h2>
              
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Database Type
                </label>
                <select
                  value={config.database.database_type}
                  onChange={(e) => updateConfig('database.database_type', e.target.value)}
                  className="w-full px-4 py-2 bg-white/20 border border-white/30 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="postgresql">PostgreSQL</option>
                  <option value="mongodb">MongoDB</option>
                  <option value="redis">Redis</option>
                  <option value="in_memory">In-Memory</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Authentication Type
                </label>
                <select
                  value={config.security.auth_type}
                  onChange={(e) => updateConfig('security.auth_type', e.target.value)}
                  className="w-full px-4 py-2 bg-white/20 border border-white/30 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="api_key">API Key</option>
                  <option value="jwt">JWT</option>
                  <option value="both">Both</option>
                </select>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Rate Limit (req/min)
                  </label>
                  <input
                    type="number"
                    value={config.security.rate_limit_per_minute}
                    onChange={(e) => updateConfig('security.rate_limit_per_minute', parseInt(e.target.value))}
                    className="w-full px-4 py-2 bg-white/20 border border-white/30 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Rate Limit Burst
                  </label>
                  <input
                    type="number"
                    value={config.security.rate_limit_burst}
                    onChange={(e) => updateConfig('security.rate_limit_burst', parseInt(e.target.value))}
                    className="w-full px-4 py-2 bg-white/20 border border-white/30 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
              </div>

              <div className="flex items-center space-x-6">
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.security.enable_rbac}
                    onChange={(e) => updateConfig('security.enable_rbac', e.target.checked)}
                    className="w-5 h-5 rounded"
                  />
                  <span className="text-gray-300">Enable RBAC</span>
                </label>

                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.database.enable_migrations}
                    onChange={(e) => updateConfig('database.enable_migrations', e.target.checked)}
                    className="w-5 h-5 rounded"
                  />
                  <span className="text-gray-300">Database Migrations</span>
                </label>

                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.database.enable_backup_scripts}
                    onChange={(e) => updateConfig('database.enable_backup_scripts', e.target.checked)}
                    className="w-5 h-5 rounded"
                  />
                  <span className="text-gray-300">Backup Scripts</span>
                </label>
              </div>

              <div className="flex space-x-4">
                <button
                  onClick={() => setStep(1)}
                  className="flex-1 bg-gray-600 hover:bg-gray-700 text-white font-bold py-3 px-6 rounded-lg transition-colors"
                >
                  ← Previous
                </button>
                <button
                  onClick={() => setStep(3)}
                  className="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-6 rounded-lg transition-colors"
                >
                  Next: CI/CD →
                </button>
              </div>
            </div>
          )}

          {/* Step 3: CI/CD & Kubernetes */}
          {step === 3 && (
            <div className="space-y-6">
              <h2 className="text-2xl font-bold text-white mb-6">⚙️ CI/CD & Deployment</h2>
              
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  CI/CD Platform
                </label>
                <select
                  value={config.cicd.platform}
                  onChange={(e) => updateConfig('cicd.platform', e.target.value)}
                  className="w-full px-4 py-2 bg-white/20 border border-white/30 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="github_actions">GitHub Actions</option>
                  <option value="gitlab_ci">GitLab CI</option>
                  <option value="both">Both</option>
                </select>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Coverage Threshold (%)
                  </label>
                  <input
                    type="number"
                    value={config.cicd.coverage_threshold}
                    onChange={(e) => updateConfig('cicd.coverage_threshold', parseInt(e.target.value))}
                    className="w-full px-4 py-2 bg-white/20 border border-white/30 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                    min="0"
                    max="100"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Deployment Target
                  </label>
                  <select
                    value={config.deployment_target}
                    onChange={(e) => updateConfig('deployment_target', e.target.value)}
                    className="w-full px-4 py-2 bg-white/20 border border-white/30 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="docker">Docker Only</option>
                    <option value="kubernetes">Kubernetes Only</option>
                    <option value="both">Both</option>
                  </select>
                </div>
              </div>

              <div className="space-y-3">
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.cicd.enable_sbom}
                    onChange={(e) => updateConfig('cicd.enable_sbom', e.target.checked)}
                    className="w-5 h-5 rounded"
                  />
                  <span className="text-gray-300">Generate SBOM</span>
                </label>

                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.cicd.enable_signing}
                    onChange={(e) => updateConfig('cicd.enable_signing', e.target.checked)}
                    className="w-5 h-5 rounded"
                  />
                  <span className="text-gray-300">Sign Artifacts (Cosign)</span>
                </label>

                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.cicd.enable_security_scan}
                    onChange={(e) => updateConfig('cicd.enable_security_scan', e.target.checked)}
                    className="w-5 h-5 rounded"
                  />
                  <span className="text-gray-300">Security Scanning</span>
                </label>

                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.kubernetes.enable_hpa}
                    onChange={(e) => updateConfig('kubernetes.enable_hpa', e.target.checked)}
                    className="w-5 h-5 rounded"
                  />
                  <span className="text-gray-300">Horizontal Pod Autoscaler</span>
                </label>

                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={config.kubernetes.enable_network_policy}
                    onChange={(e) => updateConfig('kubernetes.enable_network_policy', e.target.checked)}
                    className="w-5 h-5 rounded"
                  />
                  <span className="text-gray-300">Network Policy</span>
                </label>
              </div>

              <div className="flex space-x-4">
                <button
                  onClick={() => setStep(2)}
                  className="flex-1 bg-gray-600 hover:bg-gray-700 text-white font-bold py-3 px-6 rounded-lg transition-colors"
                >
                  ← Previous
                </button>
                <button
                  onClick={() => setStep(4)}
                  className="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-6 rounded-lg transition-colors"
                >
                  Next: Review →
                </button>
              </div>
            </div>
          )}

          {/* Step 4: Review & Generate */}
          {step === 4 && (
            <div className="space-y-6">
              <h2 className="text-2xl font-bold text-white mb-6">✅ Review & Generate</h2>
              
              <div className="bg-black/30 rounded-lg p-6 space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <span className="text-gray-400 text-sm">Service Name:</span>
                    <p className="text-white font-mono">{config.metadata.name}</p>
                  </div>
                  <div>
                    <span className="text-gray-400 text-sm">Language:</span>
                    <p className="text-white">Python + FastAPI</p>
                  </div>
                  <div>
                    <span className="text-gray-400 text-sm">Database:</span>
                    <p className="text-white">{config.database.database_type}</p>
                  </div>
                  <div>
                    <span className="text-gray-400 text-sm">Authentication:</span>
                    <p className="text-white">{config.security.auth_type}</p>
                  </div>
                  <div>
                    <span className="text-gray-400 text-sm">CI/CD:</span>
                    <p className="text-white">{config.cicd.platform}</p>
                  </div>
                  <div>
                    <span className="text-gray-400 text-sm">Deployment:</span>
                    <p className="text-white">{config.deployment_target}</p>
                  </div>
                </div>

                <div className="border-t border-white/20 pt-4 mt-4">
                  <span className="text-gray-400 text-sm">What you'll get:</span>
                  <ul className="mt-2 space-y-1 text-gray-300 text-sm">
                    <li>✓ ~50 files with production-ready code</li>
                    <li>✓ Complete CI/CD pipeline (build, test, security scan, deploy)</li>
                    <li>✓ Kubernetes manifests (Deployment, Service, HPA, PDB, NetworkPolicy)</li>
                    <li>✓ Database migrations and backup scripts</li>
                    <li>✓ Comprehensive documentation (API, Architecture, Runbook, Security)</li>
                    <li>✓ Prometheus metrics and health checks</li>
                    <li>✓ {config.cicd.coverage_threshold}%+ test coverage requirement</li>
                  </ul>
                </div>
              </div>

              <div className="flex space-x-4">
                <button
                  onClick={() => setStep(3)}
                  className="flex-1 bg-gray-600 hover:bg-gray-700 text-white font-bold py-3 px-6 rounded-lg transition-colors"
                  disabled={generating}
                >
                  ← Previous
                </button>
                <button
                  onClick={handleGenerate}
                  disabled={generating}
                  className="flex-1 bg-green-600 hover:bg-green-700 text-white font-bold py-3 px-6 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {generating ? '⏳ Generating...' : '🚀 Generate Microservice'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="text-center mt-8 text-gray-400">
          <p>Powered by Emergent AI | Production-Grade Microservice Generator</p>
        </div>
      </div>
    </div>
  );
}

export default App;
