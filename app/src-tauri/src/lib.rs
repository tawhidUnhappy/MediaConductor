pub mod commands;
pub mod state;

use state::AppState;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_opener::init())
        .manage(AppState::new())
        .invoke_handler(tauri::generate_handler![
            // project / config
            commands::get_project_root,
            commands::set_project_root,
            commands::read_config,
            commands::write_config,
            commands::chapter_status,
            // file system
            commands::pick_directory,
            commands::pick_file,
            commands::open_directory,
            // doctor
            commands::run_doctor,
            // job runner
            commands::run_job,
            commands::stop_job,
            commands::is_job_running,
            commands::job_status,
            commands::get_terminal_history,
            // bootstrap
            commands::bootstrap_check,
            commands::bootstrap_install,
        ])
        .run(tauri::generate_context!())
        .expect("error running mangaEasy");
}
