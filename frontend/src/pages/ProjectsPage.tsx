import { useState } from 'react'
import { useProjects, useCreateProject } from '../hooks/useProjects'
import ProjectList from '../components/projects/ProjectList'
import { ProjectListSkeleton } from '../components/common/Skeleton'
import Button from '../components/common/Button'
import Input from '../components/common/Input'
import FolderPicker from '../components/projects/FolderPicker'
import { useToast } from '../components/common/Toast'

export default function ProjectsPage() {
  const { data, isLoading } = useProjects()
  const createProject = useCreateProject()
  const { success, error: showError } = useToast()
  const [showForm, setShowForm] = useState(false)
  const [showPicker, setShowPicker] = useState(false)
  const [name, setName] = useState('')
  const [path, setPath] = useState('')
  const [description, setDescription] = useState('')

  const handleCreate = async () => {
    if (!name.trim() || !path.trim()) return
    try {
      await createProject.mutateAsync({
        name: name.trim(),
        path: path.trim(),
        description: description.trim() || undefined,
      })
      setName('')
      setPath('')
      setDescription('')
      setShowForm(false)
      success(`Project "${name.trim()}" registered`)
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to create project')
    }
  }

  const handleFolderSelect = (selectedPath: string) => {
    setPath(selectedPath)
    setShowPicker(false)
    // Auto-fill name from directory name if empty
    if (!name.trim()) {
      const dirName = selectedPath.split('/').filter(Boolean).pop()
      if (dirName) setName(dirName)
    }
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zurk-50">Projects</h1>
          <p className="text-sm text-zurk-400 mt-1">
            Registered project directories
          </p>
        </div>
        <Button
          variant={showForm ? 'ghost' : 'primary'}
          size="sm"
          onClick={() => setShowForm(!showForm)}
        >
          {showForm ? 'Cancel' : 'Add Project'}
        </Button>
      </div>

      {/* Add project form */}
      {showForm && (
        <div className="bg-zurk-800/80 border border-zurk-700/70 rounded-xl p-4 space-y-4">
          <Input
            label="Project Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="My App"
          />
          <div className="space-y-1.5">
            <label className="block text-sm font-medium text-zurk-200">
              Directory Path
            </label>
            <div className="flex gap-2">
              <input
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder="/Users/you/projects/my-app"
                className="flex-1 bg-zurk-800/80 border border-zurk-600/70 rounded-lg px-3 py-2 text-sm
                  text-zurk-100 placeholder:text-zurk-500
                  focus:outline-none focus:ring-2 focus:ring-accent-500/20 focus:border-accent-400"
              />
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowPicker(true)}
              >
                Browse
              </Button>
            </div>
          </div>
          <Input
            label="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="A brief description..."
          />
          <div className="flex gap-2 pt-2">
            <Button
              onClick={handleCreate}
              loading={createProject.isPending}
              disabled={!name.trim() || !path.trim()}
            >
              Register Project
            </Button>
            <Button variant="ghost" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
          </div>
          {createProject.error && (
            <p className="text-sm text-status-error">
              {createProject.error instanceof Error
                ? createProject.error.message
                : 'Failed to create project'}
            </p>
          )}
        </div>
      )}

      {/* Project list */}
      {isLoading ? (
        <ProjectListSkeleton count={3} />
      ) : (
        <ProjectList
          projects={data?.projects ?? []}
          onAddFirst={() => setShowForm(true)}
        />
      )}

      {/* Folder picker modal */}
      {showPicker && (
        <FolderPicker
          onSelect={handleFolderSelect}
          onClose={() => setShowPicker(false)}
        />
      )}
    </div>
  )
}
